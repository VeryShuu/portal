"""Folder CRUD + tree/detail endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, RedisDep, require_role
from app.models.files import FileFolder
from app.schemas.files import (
    CreateFolderRequest,
    FileFolderPublic,
    FileFolderTree,
    FileFolderTreeNode,
    FolderDetailResponse,
    UpdateFolderRequest,
)
from app.services.audit import push_audit_event
from app.services.files_acl import (
    batch_resolve_folder_permissions,
    invalidate_folder_cache,
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.files_acl_persistence import drop_folder_perms
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import (
    ModuleCheck,
    _build_breadcrumbs,
    _enrich_nc_items_with_db,
    _filter_nc_subfolders_by_acl,
    _folder_to_public,
    _get_folder_or_404,
    _normalize_nc_items,
    logger,
    sanitize_name,
)

router = APIRouter(tags=["files"])


# ── Folder tree ────────────────────────────────────────────────────────────────


@router.get("/files/tree", response_model=FileFolderTree, dependencies=[ModuleCheck])
async def get_folder_tree(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    parent_id: uuid.UUID | None = Query(default=None),
) -> FileFolderTree:
    res = await db.execute(
        select(FileFolder).where(FileFolder.deleted_at.is_(None)).order_by(FileFolder.name)
    )
    all_folders = list(res.scalars().all())

    perms = await batch_resolve_folder_permissions(user, all_folders, db, redis)
    accessible: dict[uuid.UUID, str] = {
        f.id: p for f in all_folders if (p := perms.get(f.id)) and perm_gte(p, "viewer")
    }

    def build_node(folder: FileFolder) -> FileFolderTreeNode:
        children = [
            build_node(cf)
            for cf in all_folders
            if cf.parent_id == folder.id and cf.id in accessible
        ]
        return FileFolderTreeNode(
            id=folder.id,
            parent_id=folder.parent_id,
            name=folder.name,
            nc_path=folder.nc_path,
            permission=accessible[folder.id],
            inherit_permissions=folder.inherit_permissions,
            children=children,
        )

    nodes = [build_node(f) for f in all_folders if f.parent_id == parent_id and f.id in accessible]
    return FileFolderTree(items=nodes)


# ── Folder detail ──────────────────────────────────────────────────────────────


@router.get(
    "/files/folders/{folder_id}", response_model=FolderDetailResponse, dependencies=[ModuleCheck]
)
async def get_folder_detail(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FolderDetailResponse:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "viewer", db, redis)
    perm = await resolve_folder_permission(user, folder, db, redis)

    nc = get_nc_service()
    nc_error = False
    try:
        items = await nc.list_folder(folder.nc_path)
    except NextcloudError as e:
        logger.warning("nc.list_folder_failed", path=folder.nc_path, status=e.status)
        items = []
        nc_error = True

    breadcrumbs = await _build_breadcrumbs(folder, db, user, redis)
    items = _normalize_nc_items(items)
    items = await _filter_nc_subfolders_by_acl(items, folder, user, db, redis)
    items = await _enrich_nc_items_with_db(items, folder, db)

    return FolderDetailResponse(
        folder=await _folder_to_public(folder, perm),
        items=items,
        breadcrumbs=breadcrumbs,
        nc_error=nc_error,
    )


# ── Create folder ──────────────────────────────────────────────────────────────


@router.post(
    "/files/folders",
    response_model=FileFolderPublic,
    status_code=201,
    dependencies=[ModuleCheck, Depends(require_role("editor", "admin"))],
)
async def create_folder(
    body: CreateFolderRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileFolderPublic:
    parent_nc_path = ""
    if body.parent_id:
        parent = await _get_folder_or_404(db, body.parent_id)
        await require_folder_permission(user, parent, "editor", db, redis)
        parent_nc_path = parent.nc_path

    safe_name = sanitize_name(body.name)
    nc_path = f"{parent_nc_path}/{safe_name}".lstrip("/") if parent_nc_path else safe_name

    existing = await db.execute(
        select(FileFolder).where(FileFolder.nc_path == nc_path, FileFolder.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder with this name already exists")

    # ADR: единый порядок «БД → NC» с компенсацией.
    # 1) reserve in DB (flush — ловим IntegrityError из unique constraint);
    # 2) create in NC; 3) commit. При ошибке NC — rollback DB.
    now = datetime.now(UTC)
    folder = FileFolder(
        parent_id=body.parent_id,
        name=body.name,
        nc_path=nc_path,
        description=body.description,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(folder)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Folder with this name already exists"
        ) from exc

    nc = get_nc_service()
    try:
        await nc.create_folder(nc_path)
    except NextcloudError as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}") from e

    try:
        await db.commit()
    except Exception as commit_exc:
        await db.rollback()
        # DB-коммит после успешного NC — компенсируем удалением папки в NC.
        try:
            await nc.delete(nc_path)
        except Exception as nc_rollback_exc:
            logger.error(
                "files.create_db_commit_failed_nc_rollback_failed",
                nc_path=nc_path,
                error=str(nc_rollback_exc),
            )
        raise HTTPException(
            status_code=500, detail="Folder create failed"
        ) from commit_exc
    await db.refresh(folder)

    await push_audit_event(
        redis,
        event_type="files.folder_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="folder",
        resource_id=str(folder.id),
        metadata={"nc_path": nc_path},
    )
    return await _folder_to_public(folder, "manager")


# ── Update folder ──────────────────────────────────────────────────────────────


@router.patch(
    "/files/folders/{folder_id}",
    response_model=FileFolderPublic,
    dependencies=[ModuleCheck],
)
async def update_folder(
    folder_id: uuid.UUID,
    body: UpdateFolderRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileFolderPublic:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    # ADR: единый порядок «БД → NC» с компенсацией.
    # rename: 1) commit DB; 2) NC.move; при сбое NC — компенсация (rollback DB).
    renamed = False
    old_name = folder.name
    old_nc_path = folder.nc_path
    new_nc_path = old_nc_path
    if body.name is not None and body.name != folder.name:
        safe_name = sanitize_name(body.name)
        parent_path = old_nc_path.rsplit("/", 1)[0] if "/" in old_nc_path else ""
        new_nc_path = f"{parent_path}/{safe_name}".lstrip("/") if parent_path else safe_name
        folder.nc_path = new_nc_path
        folder.name = body.name
        renamed = True

    if body.description is not None:
        folder.description = body.description

    folder.updated_at = datetime.now(UTC)
    await db.commit()

    if renamed:
        nc = get_nc_service()
        try:
            await nc.move(old_nc_path, new_nc_path)
        except NextcloudError as e:
            # Компенсация: возвращаем старое имя/путь в БД.
            folder.name = old_name
            folder.nc_path = old_nc_path
            folder.updated_at = datetime.now(UTC)
            try:
                await db.commit()
            except Exception as rollback_exc:
                logger.error(
                    "files.rename_nc_failed_db_compensation_failed",
                    old_nc_path=old_nc_path,
                    new_nc_path=new_nc_path,
                    error=str(rollback_exc),
                )
            raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}") from e

    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder.id, db)

    if renamed:
        await push_audit_event(
            redis,
            event_type="files.folder_renamed",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="folder",
            resource_id=str(folder.id),
            metadata={"old_nc_path": old_nc_path, "new_nc_path": folder.nc_path},
        )

    perm = await resolve_folder_permission(user, folder, db, redis)
    return await _folder_to_public(folder, perm)


# ── Delete folder ──────────────────────────────────────────────────────────────


@router.delete("/files/folders/{folder_id}", status_code=204, dependencies=[ModuleCheck])
async def delete_folder(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    hard: bool = Query(default=False),
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    nc = get_nc_service()
    now = datetime.now(UTC)
    folder.deleted_at = now
    await db.execute(
        text(
            "WITH RECURSIVE descendants AS ("
            "  SELECT id FROM file_folders"
            "  WHERE parent_id = :root_id AND deleted_at IS NULL"
            "  UNION ALL"
            "  SELECT f.id FROM file_folders f"
            "  JOIN descendants d ON f.parent_id = d.id"
            "  WHERE f.deleted_at IS NULL"
            ")"
            " UPDATE file_folders SET deleted_at = :now"
            " WHERE id IN (SELECT id FROM descendants)"
        ),
        {"root_id": folder.id, "now": now},
    )
    await db.commit()

    try:
        await nc.delete(folder.nc_path)
    except NextcloudError as e:
        if e.status != 404:
            logger.warning("files.folder_delete_nc_error", folder_id=str(folder.id), error=str(e))
            # Дрейф: БД помечена как удалённая, NC ещё содержит папку.
            # Не откатываем БД — sync с NC устранит расхождение, либо повторное удаление.
            await push_audit_event(
                redis,
                event_type="files.folder_delete_nc_drift",
                user_id=str(user.id),
                user_email=user.email,
                resource_type="folder",
                resource_id=str(folder.id),
                metadata={"nc_path": folder.nc_path, "nc_status": e.status},
            )
    await invalidate_folder_cache(redis, folder.id, db)
    await drop_folder_perms(folder.nc_path)
    await push_audit_event(
        redis,
        event_type="files.folder_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="folder",
        resource_id=str(folder.id),
    )
