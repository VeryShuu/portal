"""Folder CRUD, move, restore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER
from app.models.photos import Photo, PhotoFolder
from app.schemas.photos import (
    CreateFolderRequest,
    FolderPublic,
    FolderTree,
    FolderTreeNode,
    UpdateFolderRequest,
)
from app.services import photos_storage
from app.services.audit import push_audit_event
from app.services.photos_acl import (
    filter_accessible_folders_with_perm,
    invalidate_folder_cache,
    require_folder_permission,
    resolve_folder_permission,
)

from ._common import _folder_to_public, _slugify, _would_create_cycle, logger

router = APIRouter()


@router.get("/folders/tree", response_model=FolderTree)
async def list_folder_tree(db: DbDep, user: CurrentUser, redis: RedisDep) -> FolderTree:
    res = await db.execute(
        select(PhotoFolder)
        .where(PhotoFolder.deleted_at.is_(None))
        .order_by(PhotoFolder.path, PhotoFolder.name)
    )
    folders = list(res.scalars().all())
    accessible_with_perm = await filter_accessible_folders_with_perm(user, folders, db, redis)
    by_id: dict[uuid.UUID, FolderTreeNode] = {}
    for f, perm in accessible_with_perm:
        by_id[f.id] = FolderTreeNode(
            id=f.id,
            parent_id=f.parent_id,
            name=f.name,
            slug=f.slug,
            path=f.path,
            cover_photo_id=f.cover_photo_id,
            permission=perm,
            children=[],
        )
    roots: list[FolderTreeNode] = []
    for f, _ in accessible_with_perm:
        node = by_id[f.id]
        if f.parent_id and f.parent_id in by_id:
            by_id[f.parent_id].children.append(node)
        else:
            roots.append(node)
    return FolderTree(items=roots)


@router.get("/folders/deleted", response_model=list[FolderPublic])
async def list_deleted_folders(db: DbDep, user: AdminDep) -> list[FolderPublic]:
    res = await db.execute(
        select(PhotoFolder)
        .where(PhotoFolder.deleted_at.isnot(None))
        .order_by(PhotoFolder.deleted_at.desc())
    )
    folders = res.scalars().all()
    return [_folder_to_public(f, permission=PERM_MANAGER) for f in folders]


@router.get("/folders/{folder_id}", response_model=FolderPublic)
async def get_folder(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    perm = await resolve_folder_permission(user, folder, db, redis)
    if perm is None:
        raise HTTPException(status_code=403, detail="No access")
    pcount = await db.scalar(
        select(func.count(Photo.id)).where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
    )
    ccount = await db.scalar(
        select(func.count(PhotoFolder.id)).where(
            PhotoFolder.parent_id == folder_id, PhotoFolder.deleted_at.is_(None)
        )
    )
    return _folder_to_public(
        folder, photos_count=int(pcount or 0), children_count=int(ccount or 0), permission=perm
    )


@router.post("/folders", response_model=FolderPublic, status_code=201)
async def create_folder(
    data: CreateFolderRequest, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:
    parent: PhotoFolder | None = None
    parent_path = ""
    if data.parent_id:
        pres = await db.execute(
            select(PhotoFolder).where(
                PhotoFolder.id == data.parent_id, PhotoFolder.deleted_at.is_(None)
            )
        )
        parent = pres.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        await require_folder_permission(user, parent, PERM_MANAGER, db, redis)
        parent_path = parent.path or parent.slug
    else:
        if user.role not in ("admin", "editor"):
            raise HTTPException(
                status_code=403, detail="Only admin or editor can create root folders"
            )

    slug = _slugify(data.name)
    base_slug = slug
    i = 1
    while True:
        exists = await db.scalar(
            select(func.count(PhotoFolder.id)).where(
                PhotoFolder.parent_id == (parent.id if parent else None),
                PhotoFolder.slug == slug,
                PhotoFolder.deleted_at.is_(None),
            )
        )
        if not exists:
            break
        i += 1
        slug = f"{base_slug}-{i}"
        if i > 9999:
            slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
            break

    new_path = f"{parent_path}/{slug}" if parent_path else slug

    parent_fs = (parent.fs_path if parent and parent.fs_path else "") or ""
    fs_seg = photos_storage.sanitize_folder_name(data.name)
    base_seg = fs_seg
    j = 2
    sib_q = await db.execute(
        select(PhotoFolder.fs_path).where(
            PhotoFolder.parent_id == (parent.id if parent else None),
            PhotoFolder.deleted_at.is_(None),
        )
    )
    used_segs = {(p or "").split("/")[-1] for (p,) in sib_q.all()}
    while fs_seg in used_segs:
        fs_seg = f"{base_seg} ({j})"
        j += 1
        if j > 9999:
            fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
            break
    new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg

    folder = PhotoFolder(
        parent_id=parent.id if parent else None,
        name=data.name,
        slug=slug,
        path=new_path,
        fs_path=new_fs_path,
        description=data.description,
        created_by=user.id,
    )
    db.add(folder)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Folder with this name already exists in the parent",
        ) from None
    await db.refresh(folder)
    try:
        photos_storage.folder_fs_path(folder.fs_path).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("photos.folder_mkdir_failed", folder_id=str(folder.id), error=str(exc))
    await push_audit_event(
        redis,
        event_type="photos.folder_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder.id),
        resource_title=folder.name,
        ip_address=request.client.host if request.client else None,
    )
    return _folder_to_public(folder, permission=PERM_MANAGER)


@router.patch("/folders/{folder_id}", response_model=FolderPublic)
async def update_folder(
    folder_id: uuid.UUID,
    data: UpdateFolderRequest,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> FolderPublic:
    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    initial_fs_path = folder.fs_path or ""

    if "parent_id" in data.model_fields_set:
        new_parent_id = data.parent_id

        if new_parent_id != folder.parent_id:
            if await _would_create_cycle(db, folder_id, new_parent_id):
                raise HTTPException(status_code=400, detail="Moving folder would create a cycle")

            new_parent: PhotoFolder | None = None
            new_parent_path = ""
            new_parent_fs = ""

            if new_parent_id is not None:
                np_res = await db.execute(
                    select(PhotoFolder).where(
                        PhotoFolder.id == new_parent_id, PhotoFolder.deleted_at.is_(None)
                    )
                )
                new_parent = np_res.scalar_one_or_none()
                if not new_parent:
                    raise HTTPException(status_code=404, detail="New parent folder not found")
                if user.role != "admin":
                    await require_folder_permission(user, new_parent, PERM_MANAGER, db, redis)
                new_parent_path = new_parent.path or new_parent.slug
                new_parent_fs = new_parent.fs_path or ""
            else:
                if user.role != "admin":
                    raise HTTPException(
                        status_code=403, detail="Only admin can move folders to root"
                    )

            base_slug = _slugify(folder.name)
            new_slug = base_slug
            i = 1
            while True:
                slug_cnt = await db.scalar(
                    select(func.count(PhotoFolder.id)).where(
                        PhotoFolder.parent_id == new_parent_id,
                        PhotoFolder.slug == new_slug,
                        PhotoFolder.id != folder_id,
                        PhotoFolder.deleted_at.is_(None),
                    )
                )
                if not slug_cnt:
                    break
                i += 1
                new_slug = f"{base_slug}-{i}"
                if i > 9999:
                    new_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                    break

            fs_seg = photos_storage.sanitize_folder_name(folder.name)
            base_seg = fs_seg
            j = 2
            sib_q2 = await db.execute(
                select(PhotoFolder.fs_path).where(
                    PhotoFolder.parent_id == new_parent_id,
                    PhotoFolder.id != folder_id,
                    PhotoFolder.deleted_at.is_(None),
                )
            )
            used_segs = {(p or "").split("/")[-1] for (p,) in sib_q2.all()}
            while fs_seg in used_segs:
                fs_seg = f"{base_seg} ({j})"
                j += 1
                if j > 9999:
                    fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
                    break

            old_path = folder.path or ""
            old_fs_path = folder.fs_path or ""
            new_path = f"{new_parent_path}/{new_slug}" if new_parent_path else new_slug
            new_fs_path = f"{new_parent_fs}/{fs_seg}" if new_parent_fs else fs_seg

            if old_path:
                esc_path = old_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                update_values: dict = {
                    "path": func.concat(
                        new_path, func.substring(PhotoFolder.path, len(old_path) + 1)
                    ),
                }
                if old_fs_path:
                    update_values["fs_path"] = func.concat(
                        new_fs_path,
                        func.substring(PhotoFolder.fs_path, len(old_fs_path) + 1),
                    )
                await db.execute(
                    update(PhotoFolder)
                    .where(PhotoFolder.path.like(f"{esc_path}/%", escape="\\"))
                    .values(**update_values)
                )

            folder.parent_id = new_parent_id
            folder.slug = new_slug
            folder.path = new_path
            folder.fs_path = new_fs_path

    if data.name is not None and data.name != folder.name:
        folder.name = data.name
        parent_fs = ""
        if folder.parent_id:
            parent_fs_row = await db.scalar(
                select(PhotoFolder.fs_path).where(PhotoFolder.id == folder.parent_id)
            )
            parent_fs = (parent_fs_row or "") or ""

        fs_seg = photos_storage.sanitize_folder_name(data.name)
        base_seg = fs_seg
        j = 2
        sib_q3 = await db.execute(
            select(PhotoFolder.fs_path).where(
                PhotoFolder.parent_id == folder.parent_id,
                PhotoFolder.id != folder.id,
                PhotoFolder.deleted_at.is_(None),
            )
        )
        used_segs = {(p or "").split("/")[-1] for (p,) in sib_q3.all()}
        while fs_seg in used_segs:
            fs_seg = f"{base_seg} ({j})"
            j += 1
            if j > 9999:
                fs_seg = f"{base_seg}-{uuid.uuid4().hex[:8]}"
                break

        new_fs_path = f"{parent_fs}/{fs_seg}" if parent_fs else fs_seg
        current_fs = folder.fs_path or ""
        if new_fs_path != current_fs:
            folder.fs_path = new_fs_path
            if current_fs:
                escaped = current_fs.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                await db.execute(
                    update(PhotoFolder)
                    .where(PhotoFolder.fs_path.like(f"{escaped}/%", escape="\\"))
                    .values(
                        fs_path=func.concat(
                            new_fs_path, func.substring(PhotoFolder.fs_path, len(current_fs) + 1)
                        )
                    )
                )

    if data.description is not None:
        folder.description = data.description

    if data.cover_photo_id is not None:
        ph = await db.scalar(
            select(Photo).where(
                Photo.id == data.cover_photo_id,
                Photo.folder_id == folder_id,
                Photo.deleted_at.is_(None),
            )
        )
        if not ph:
            raise HTTPException(status_code=400, detail="Cover photo must belong to this folder")
        folder.cover_photo_id = data.cover_photo_id

    folder.updated_at = datetime.now(UTC)

    final_fs_path = folder.fs_path or ""
    needs_fs_rename = bool(initial_fs_path and final_fs_path and final_fs_path != initial_fs_path)

    # Split-brain protection: rename FS BEFORE commit. If rename fails — rollback
    # DB so DB.path stays in sync with FS.path. If commit fails after a successful
    # rename — try to rename back; on failure log critical (irrecoverable).
    if needs_fs_rename:
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
    else:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id, db)
    return _folder_to_public(folder, permission=PERM_MANAGER)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> None:

    res = await db.execute(
        select(PhotoFolder).where(PhotoFolder.id == folder_id, PhotoFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    delete_ts = datetime.now(UTC)
    folder.deleted_at = delete_ts
    await db.execute(
        update(Photo)
        .where(Photo.folder_id == folder_id, Photo.deleted_at.is_(None))
        .values(deleted_at=delete_ts)
    )
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="photos.folder_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
    )


@router.post("/folders/{folder_id}/restore", response_model=FolderPublic)
async def restore_folder(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: AdminDep, redis: RedisDep
) -> FolderPublic:
    res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == folder_id))
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.deleted_at is None:
        raise HTTPException(status_code=400, detail="Folder is not deleted")
    cascade_ts = folder.deleted_at
    folder.deleted_at = None

    descendants_res = await db.execute(
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
        {"root_id": folder_id},
    )
    descendant_ids = [row[0] for row in descendants_res.fetchall()]

    if descendant_ids:
        await db.execute(
            update(PhotoFolder)
            .where(PhotoFolder.id.in_(descendant_ids), PhotoFolder.deleted_at == cascade_ts)
            .values(deleted_at=None)
        )
        await db.execute(
            update(Photo)
            .where(Photo.folder_id.in_(descendant_ids), Photo.deleted_at == cascade_ts)
            .values(deleted_at=None)
        )

    await db.execute(
        update(Photo)
        .where(Photo.folder_id == folder_id, Photo.deleted_at == cascade_ts)
        .values(deleted_at=None)
    )

    await db.commit()
    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="photos.folder_restored",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
    )
    return _folder_to_public(folder, permission=PERM_MANAGER)
