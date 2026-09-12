from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import Photo, PhotoFolder


async def fetch_active_folders_ordered(db: AsyncSession) -> Sequence[PhotoFolder]:
    res = await db.execute(
        select(PhotoFolder)
        .where(PhotoFolder.deleted_at.is_(None))
        .order_by(PhotoFolder.path, PhotoFolder.name)
    )
    return res.scalars().all()


async def fetch_deleted_folders_ordered(db: AsyncSession) -> Sequence[PhotoFolder]:
    res = await db.execute(
        select(PhotoFolder)
        .where(PhotoFolder.deleted_at.isnot(None))
        .order_by(PhotoFolder.deleted_at.desc())
    )
    return res.scalars().all()


async def fetch_active_folder(db: AsyncSession, folder_id: uuid.UUID) -> PhotoFolder | None:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    return res.scalar_one_or_none()


async def fetch_folder_any(db: AsyncSession, folder_id: uuid.UUID) -> PhotoFolder | None:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id))
    return res.scalar_one_or_none()


async def count_active_photos_in_folder(db: AsyncSession, folder_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count(Photo.id)).where(
                Photo.folder_id == folder_id,
                Photo.deleted_at.is_(None),
            )
        )
        or 0
    )


async def count_active_subfolders(db: AsyncSession, folder_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count(PhotoFolder.id)).where(
                PhotoFolder.parent_id == folder_id, PhotoFolder.deleted_at.is_(None)
            )
        )
        or 0
    )


async def count_siblings_with_slug(
    db: AsyncSession,
    *,
    parent_id: uuid.UUID | None,
    slug: str,
    exclude_id: uuid.UUID | None = None,
) -> int:
    q = select(func.count(PhotoFolder.id)).where(
        PhotoFolder.parent_id == parent_id,
        PhotoFolder.slug == slug,
        PhotoFolder.deleted_at.is_(None),
    )
    if exclude_id is not None:
        q = q.where(PhotoFolder.id != exclude_id)
    return int(await db.scalar(q) or 0)


async def fetch_sibling_fs_segments(
    db: AsyncSession,
    *,
    parent_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> set[str]:
    q = select(PhotoFolder.fs_path).where(
        PhotoFolder.parent_id == parent_id,
        PhotoFolder.deleted_at.is_(None),
    )
    if exclude_id is not None:
        q = q.where(PhotoFolder.id != exclude_id)
    res = await db.execute(q)
    return {(p or "").split("/")[-1] for (p,) in res.all()}


async def fetch_parent_fs_path(db: AsyncSession, parent_id: uuid.UUID) -> str:
    row = await db.scalar(select(PhotoFolder.fs_path).where(PhotoFolder.id == parent_id))
    return (row or "") or ""


async def cascade_descendant_paths(
    db: AsyncSession,
    *,
    old_path: str,
    new_path: str,
    old_fs_path: str | None,
    new_fs_path: str | None,
) -> None:
    if not old_path:
        return
    esc_path = old_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    update_values: dict = {
        "path": func.concat(new_path, func.substring(PhotoFolder.path, len(old_path) + 1)),
    }
    if old_fs_path and new_fs_path:
        update_values["fs_path"] = func.concat(
            new_fs_path,
            func.substring(PhotoFolder.fs_path, len(old_fs_path) + 1),
        )
    await db.execute(
        update(PhotoFolder)
        .where(PhotoFolder.path.like(f"{esc_path}/%", escape="\\"))
        .values(**update_values)
    )


async def cascade_descendant_fs_paths(
    db: AsyncSession, *, old_fs_path: str, new_fs_path: str
) -> None:
    if not old_fs_path:
        return
    escaped = old_fs_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    await db.execute(
        update(PhotoFolder)
        .where(PhotoFolder.fs_path.like(f"{escaped}/%", escape="\\"))
        .values(
            fs_path=func.concat(
                new_fs_path,
                func.substring(PhotoFolder.fs_path, len(old_fs_path) + 1),
            )
        )
    )


async def fetch_cover_photo_in_folder(
    db: AsyncSession, *, folder_id: uuid.UUID, photo_id: uuid.UUID
) -> Photo | None:
    res = await db.execute(
        select(Photo).where(
            Photo.id == photo_id,
            Photo.folder_id == folder_id,
            Photo.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def fetch_descendant_ids(db: AsyncSession, root_id: uuid.UUID) -> list[uuid.UUID]:
    res = await db.execute(
        text(
            """
            WITH RECURSIVE descendants AS (
                SELECT id FROM photo_folders WHERE id = :root_id
                UNION ALL
                SELECT pf.id
                FROM photo_folders pf
                INNER JOIN descendants d ON pf.parent_id = d.id
            )
            SELECT id FROM descendants WHERE id != :root_id
            """
        ),
        {"root_id": root_id},
    )
    return [row[0] for row in res.fetchall()]


async def soft_delete_folder_photos(
    db: AsyncSession, *, folder_id: uuid.UUID, ts: datetime
) -> None:
    await db.execute(
        update(Photo)
        .where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
        .values(deleted_at=ts)
    )


async def restore_descendants(
    db: AsyncSession, *, descendant_ids: list[uuid.UUID], cascade_ts: datetime
) -> None:
    if not descendant_ids:
        return
    await db.execute(
        update(PhotoFolder)
        .where(
            PhotoFolder.id.in_(descendant_ids),
            PhotoFolder.deleted_at == cascade_ts,
        )
        .values(deleted_at=None)
    )
    await db.execute(
        update(Photo)
        .where(
            Photo.folder_id.in_(descendant_ids),
            Photo.deleted_at == cascade_ts,
        )
        .values(deleted_at=None)
    )


async def restore_direct_photos(
    db: AsyncSession, *, folder_id: uuid.UUID, cascade_ts: datetime
) -> None:
    await db.execute(
        update(Photo)
        .where(Photo.folder_id == folder_id, Photo.deleted_at == cascade_ts)
        .values(deleted_at=None)
    )


async def fetch_photos_in_folders(
    db: AsyncSession, folder_ids: Sequence[uuid.UUID]
) -> Sequence[Photo]:
    if not folder_ids:
        return []
    res = await db.execute(select(Photo).where(Photo.folder_id.in_(folder_ids)))
    return res.scalars().all()


async def fetch_folders_by_ids(
    db: AsyncSession, folder_ids: Sequence[uuid.UUID]
) -> Sequence[PhotoFolder]:
    if not folder_ids:
        return []
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id.in_(folder_ids)))
    return res.scalars().all()
