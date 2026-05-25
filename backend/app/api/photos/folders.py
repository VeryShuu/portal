"""Folder endpoints for the photos sub-package.

Thin HTTP layer: each route delegates business logic to ``folder_service``
and data access to ``folder_repo``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_MANAGER, PERM_UPLOADER
from app.models.photos import PhotoFolder
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
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.photos_trash import TrashService

from app.services import photos_folder_repo as folder_repo
from . import folder_service
from ._common import _folder_to_public, logger

router = APIRouter()


@router.get("/folders/tree", response_model=FolderTree)
async def list_folder_tree(db: DbDep, user: CurrentUser, redis: RedisDep) -> FolderTree:
    folders = list(await folder_repo.fetch_active_folders_ordered(db))
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
async def list_deleted_folders(
    db: DbDep, user: CurrentUser, redis: RedisDep
) -> list[FolderPublic]:

    folders = await TrashService.list_trashed_folders(db)
    if user.role == "admin":
        return [_folder_to_public(f, permission=PERM_MANAGER) for f in folders]

    trash_ids = {f.id for f in folders}
    result: list[FolderPublic] = []
    for f in folders:
        if f.parent_id in trash_ids:
            continue
        perm = await resolve_folder_permission(user, f, db, redis)
        if not perm_gte(perm, PERM_MANAGER):
            continue
        result.append(_folder_to_public(f, permission=PERM_MANAGER))
    return result


@router.get("/folders/{folder_id}", response_model=FolderPublic)
async def get_folder(
    folder_id: uuid.UUID, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:
    folder = await folder_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    perm = await resolve_folder_permission(user, folder, db, redis)
    if perm is None:
        raise HTTPException(status_code=403, detail="No access")
    pcount = await folder_repo.count_active_photos_in_folder(db, folder_id)
    ccount = await folder_repo.count_active_subfolders(db, folder_id)
    return _folder_to_public(folder, photos_count=pcount, children_count=ccount, permission=perm)


@router.post("/folders", response_model=FolderPublic, status_code=201)
async def create_folder(
    data: CreateFolderRequest, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:
    parent: PhotoFolder | None = None
    parent_path = ""
    if data.parent_id:
        parent = await folder_repo.fetch_active_folder(db, data.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        await require_folder_permission(user, parent, PERM_UPLOADER, db, redis)
        parent_path = parent.path or parent.slug
    else:
        if user.role not in ("admin", "editor"):
            raise HTTPException(
                status_code=403, detail="Only admin or editor can create root folders"
            )

    slug = await folder_service.resolve_unique_slug(
        db, base_name=data.name, parent_id=parent.id if parent else None
    )
    fs_seg = await folder_service.resolve_unique_fs_seg(
        db, name=data.name, parent_id=parent.id if parent else None
    )

    new_path = f"{parent_path}/{slug}" if parent_path else slug
    parent_fs = (parent.fs_path if parent and parent.fs_path else "") or ""
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
    folder = await folder_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    initial_fs_path = folder.fs_path or ""

    if "parent_id" in data.model_fields_set and data.parent_id != folder.parent_id:
        await folder_service.apply_folder_move(db, user, redis, folder, data.parent_id)

    if data.name is not None and data.name != folder.name:
        await folder_service.apply_folder_rename(db, folder, data.name)

    if "description" in data.model_fields_set:
        folder.description = data.description

    if "cover_photo_id" in data.model_fields_set:
        await folder_service.apply_cover_photo(db, folder, data.cover_photo_id)

    folder.updated_at = datetime.now(UTC)

    await folder_service.commit_with_fs_rename(db, folder, initial_fs_path, folder.fs_path or "")

    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder_id, db)
    return _folder_to_public(folder, permission=PERM_MANAGER)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> None:

    folder = await folder_repo.fetch_active_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    await TrashService.soft_delete_folder(db, folder_id)
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
    folder_id: uuid.UUID, request: Request, db: DbDep, user: CurrentUser, redis: RedisDep
) -> FolderPublic:

    folder = await folder_repo.fetch_folder_any(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.deleted_at is None:
        raise HTTPException(status_code=400, detail="Folder is not deleted")

    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)

    await TrashService.restore_folder(db, folder_id)
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


@router.delete("/folders/{folder_id}/purge", status_code=204)
async def purge_folder(
    folder_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    """Permanently delete a trashed folder with all descendants and files."""

    folder = await folder_repo.fetch_folder_any(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.deleted_at is None:
        raise HTTPException(status_code=400, detail="Folder is not in trash")
    await require_folder_permission(user, folder, PERM_MANAGER, db, redis)
    purged_folders, purged_photos = await TrashService.purge_folder_subtree(db, folder_id)
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await push_audit_event(
        redis,
        event_type="photos.folder_purged",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="photo_folder",
        resource_id=str(folder_id),
        ip_address=request.client.host if request.client else None,
        metadata={"purged_folders": purged_folders, "purged_photos": purged_photos},
    )
