from __future__ import annotations

import uuid

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_MANAGER
from app.models.photos import PhotoFolder
from app.models.user import User
from app.services import photos_storage
from app.services.photos_acl import require_folder_permission

from . import folder_repo
from ._common import _slugify, _would_create_cycle, logger


async def resolve_unique_slug(
    db: AsyncSession,
    *,
    base_name: str,
    parent_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> str:
    base_slug = _slugify(base_name)
    slug = base_slug
    i = 1
    while True:
        if not await folder_repo.count_siblings_with_slug(
            db, parent_id=parent_id, slug=slug, exclude_id=exclude_id
        ):
            return slug
        i += 1
        slug = f"{base_slug}-{i}"
        if i > 9999:
            return f"{base_slug}-{uuid.uuid4().hex[:8]}"


async def resolve_unique_fs_seg(
    db: AsyncSession,
    *,
    name: str,
    parent_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> str:
    fs_seg = photos_storage.sanitize_folder_name(name)
    base_seg = fs_seg
    used_segs = await folder_repo.fetch_sibling_fs_segments(
        db, parent_id=parent_id, exclude_id=exclude_id
    )
    j = 2
    while fs_seg in used_segs:
        fs_seg = f"{base_seg} ({j})"
        j += 1
        if j > 9999:
            return f"{base_seg}-{uuid.uuid4().hex[:8]}"
    return fs_seg


async def resolve_new_parent(
    db: AsyncSession,
    user: User,
    redis: Redis,
    new_parent_id: uuid.UUID | None,
) -> tuple[str, str]:
    """Return (parent_path, parent_fs) for new parent or empty for root."""
    if new_parent_id is None:
        if user.role != "admin":
            raise HTTPException(
                status_code=403, detail="Only admin can move folders to root"
            )
        return "", ""
    new_parent = await folder_repo.fetch_active_folder(db, new_parent_id)
    if not new_parent:
        raise HTTPException(status_code=404, detail="New parent folder not found")
    if user.role != "admin":
        await require_folder_permission(user, new_parent, PERM_MANAGER, db, redis)
    return (new_parent.path or new_parent.slug), (new_parent.fs_path or "")


async def apply_folder_move(
    db: AsyncSession,
    user: User,
    redis: Redis,
    folder: PhotoFolder,
    new_parent_id: uuid.UUID | None,
) -> None:
    if await _would_create_cycle(db, folder.id, new_parent_id):
        raise HTTPException(status_code=400, detail="Moving folder would create a cycle")

    new_parent_path, new_parent_fs = await resolve_new_parent(db, user, redis, new_parent_id)

    new_slug = await resolve_unique_slug(
        db, base_name=folder.name, parent_id=new_parent_id, exclude_id=folder.id
    )
    fs_seg = await resolve_unique_fs_seg(
        db, name=folder.name, parent_id=new_parent_id, exclude_id=folder.id
    )

    old_path = folder.path or ""
    old_fs_path = folder.fs_path or ""
    new_path = f"{new_parent_path}/{new_slug}" if new_parent_path else new_slug
    new_fs_path = f"{new_parent_fs}/{fs_seg}" if new_parent_fs else fs_seg

    await folder_repo.cascade_descendant_paths(
        db,
        old_path=old_path,
        new_path=new_path,
        old_fs_path=old_fs_path,
        new_fs_path=new_fs_path,
    )

    folder.parent_id = new_parent_id
    folder.slug = new_slug
    folder.path = new_path
    folder.fs_path = new_fs_path


async def apply_folder_rename(
    db: AsyncSession, folder: PhotoFolder, new_name: str
) -> None:
    folder.name = new_name
    parent_fs = ""
    if folder.parent_id:
        parent_fs = await folder_repo.fetch_parent_fs_path(db, folder.parent_id)

    fs_seg = await resolve_unique_fs_seg(
        db, name=new_name, parent_id=folder.parent_id, exclude_id=folder.id
    )
    new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg
    current_fs = folder.fs_path or ""
    if new_fs_path != current_fs:
        folder.fs_path = new_fs_path
        if current_fs:
            await folder_repo.cascade_descendant_fs_paths(
                db, old_fs_path=current_fs, new_fs_path=new_fs_path
            )


async def apply_cover_photo(
    db: AsyncSession, folder: PhotoFolder, cover_photo_id: uuid.UUID
) -> None:
    ph = await folder_repo.fetch_cover_photo_in_folder(
        db, folder_id=folder.id, photo_id=cover_photo_id
    )
    if not ph:
        raise HTTPException(
            status_code=400, detail="Cover photo must belong to this folder"
        )
    folder.cover_photo_id = cover_photo_id


async def commit_with_fs_rename(
    db: AsyncSession, folder: PhotoFolder, initial_fs_path: str, final_fs_path: str
) -> None:
    """Commit folder changes with split-brain protection on FS rename.

    Rename FS BEFORE commit. If rename fails — rollback DB so DB.path stays
    in sync with FS.path. If commit fails after a successful rename — try to
    rename back; on failure log critical (irrecoverable).
    """
    needs_fs_rename = bool(
        initial_fs_path and final_fs_path and final_fs_path != initial_fs_path
    )

    if not needs_fs_rename:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return

    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise

    try:
        photos_storage.rename_folder_dir(initial_fs_path, final_fs_path)
    except Exception as exc:
        await db.rollback()
        logger.error(
            "photos.rename_fs_failed",
            folder_id=str(folder.id),
            old=initial_fs_path,
            new=final_fs_path,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500, detail="Failed to rename folder on filesystem"
        ) from exc

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            photos_storage.rename_folder_dir(final_fs_path, initial_fs_path)
        except Exception as revert_exc:
            logger.critical(
                "photos.rename_split_brain",
                folder_id=str(folder.id),
                old=initial_fs_path,
                new=final_fs_path,
                revert_error=str(revert_exc),
            )
        raise
