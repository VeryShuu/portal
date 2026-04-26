"""Files module router — Phase 5 (ADR-032).

All operations go through portal-svc service account.
ACL is enforced via files_acl.py (viewer/editor/manager).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import quote as urlquote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, RedisDep, require_role
from app.api.modules import load_modules
from app.core.logging import get_logger
from app.models.files import FileFolder, FileFolderPermission
from app.schemas.files import (
    CreateFolderRequest,
    FileFolderPublic,
    FileFolderTree,
    FileFolderTreeNode,
    FileOpenResponse,
    FolderDetailResponse,
    GrantPermissionRequest,
    PermissionList,
    PermissionPublic,
    UpdateFolderRequest,
    UploadResult,
    UploadResultItem,
)
from app.services import audit
from app.services.files_acl import (
    filter_accessible_folders,
    invalidate_folder_cache,
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.nextcloud import NextcloudError, get_nc_service

logger = get_logger(__name__)

router = APIRouter(tags=["files"])


def _check_module_enabled() -> None:
    modules = load_modules()
    if not modules.nextcloud.enabled:
        raise HTTPException(status_code=503, detail="Files module is disabled")


ModuleCheck = Depends(_check_module_enabled)


# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_folder_or_404(db: AsyncSession, folder_id: uuid.UUID) -> FileFolder:
    res = await db.execute(
        select(FileFolder).where(FileFolder.id == folder_id, FileFolder.deleted_at.is_(None))
    )
    folder = res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


async def _folder_to_public(folder: FileFolder, perm: str | None) -> FileFolderPublic:
    return FileFolderPublic(
        id=folder.id,
        parent_id=folder.parent_id,
        name=folder.name,
        nc_path=folder.nc_path,
        description=folder.description,
        permission=perm,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


async def _build_breadcrumbs(
    folder: FileFolder,
    db: AsyncSession,
    user: CurrentUser,  # type: ignore[type-arg]
    redis: RedisDep,  # type: ignore[type-arg]
) -> list[FileFolderPublic]:
    crumbs: list[FileFolderPublic] = []
    current_id = folder.parent_id
    visited: set[uuid.UUID] = set()
    depth = 0
    while current_id and depth < 20:
        if current_id in visited:
            break
        visited.add(current_id)
        res = await db.execute(
            select(FileFolder).where(FileFolder.id == current_id, FileFolder.deleted_at.is_(None))
        )
        parent = res.scalar_one_or_none()
        if not parent:
            break
        perm = await resolve_folder_permission(user, parent, db, redis)
        crumbs.insert(0, await _folder_to_public(parent, perm))
        current_id = parent.parent_id
        depth += 1
    return crumbs


# ── Folder tree ────────────────────────────────────────────────────────────────

@router.get("/files/tree", response_model=FileFolderTree, dependencies=[ModuleCheck])
async def get_folder_tree(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    parent_id: uuid.UUID | None = Query(default=None),
) -> FileFolderTree:
    res = await db.execute(
        select(FileFolder).where(
            FileFolder.parent_id == parent_id,
            FileFolder.deleted_at.is_(None),
        ).order_by(FileFolder.name)
    )
    folders = res.scalars().all()
    accessible = await filter_accessible_folders(user, list(folders), db, redis)

    async def build_node(folder: FileFolder, perm: str) -> FileFolderTreeNode:
        res2 = await db.execute(
            select(FileFolder).where(
                FileFolder.parent_id == folder.id,
                FileFolder.deleted_at.is_(None),
            ).order_by(FileFolder.name)
        )
        children_raw = res2.scalars().all()
        children_accessible = await filter_accessible_folders(user, list(children_raw), db, redis)
        children = [await build_node(cf, cp) for cf, cp in children_accessible]
        return FileFolderTreeNode(
            id=folder.id,
            parent_id=folder.parent_id,
            name=folder.name,
            nc_path=folder.nc_path,
            permission=perm,
            children=children,
        )

    nodes = [await build_node(f, p) for f, p in accessible]
    return FileFolderTree(items=nodes)


# ── Folder detail ──────────────────────────────────────────────────────────────

@router.get("/files/folders/{folder_id}", response_model=FolderDetailResponse, dependencies=[ModuleCheck])
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
    try:
        items = await nc.list_folder(folder.nc_path)
    except NextcloudError as e:
        logger.warning("nc.list_folder_failed", path=folder.nc_path, status=e.status)
        items = []

    breadcrumbs = await _build_breadcrumbs(folder, db, user, redis)

    return FolderDetailResponse(
        folder=await _folder_to_public(folder, perm),
        items=items,
        breadcrumbs=breadcrumbs,
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

    safe_name = body.name.replace("/", "_").replace("\\", "_")
    nc_path = f"{parent_nc_path}/{safe_name}".lstrip("/") if parent_nc_path else safe_name

    existing = await db.execute(
        select(FileFolder).where(FileFolder.nc_path == nc_path, FileFolder.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder with this name already exists")

    nc = get_nc_service()
    try:
        await nc.create_folder(nc_path)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}")

    now = datetime.now(timezone.utc)
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
    await db.commit()
    await db.refresh(folder)

    await audit.log(
        db=db, user_id=user.id, event_type="files.folder_created",
        metadata={"folder_id": str(folder.id), "nc_path": nc_path},
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

    if body.name is not None and body.name != folder.name:
        old_nc_path = folder.nc_path
        safe_name = body.name.replace("/", "_").replace("\\", "_")
        parent_path = old_nc_path.rsplit("/", 1)[0] if "/" in old_nc_path else ""
        new_nc_path = f"{parent_path}/{safe_name}".lstrip("/") if parent_path else safe_name

        nc = get_nc_service()
        try:
            await nc.move(old_nc_path, new_nc_path)
        except NextcloudError as e:
            raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}")

        folder.nc_path = new_nc_path
        folder.name = body.name

    if body.description is not None:
        folder.description = body.description

    folder.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder.id, db)

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
    try:
        await nc.delete(folder.nc_path)
    except NextcloudError as e:
        if e.status != 404:
            raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}")

    folder.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await invalidate_folder_cache(redis, folder.id, db)
    await audit.log(
        db=db, user_id=user.id, event_type="files.folder_deleted",
        metadata={"folder_id": str(folder.id)},
    )


# ── Upload files ───────────────────────────────────────────────────────────────

@router.post(
    "/files/folders/{folder_id}/upload",
    response_model=UploadResult,
    dependencies=[ModuleCheck],
)
async def upload_files(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    files: list[UploadFile],
) -> UploadResult:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    nc = get_nc_service()
    uploaded: list[UploadResultItem] = []
    failed: list[UploadResultItem] = []

    for file in files:
        filename = (file.filename or "unnamed").replace("/", "_").replace("\\", "_")
        nc_path = f"{folder.nc_path}/{filename}"
        mime = file.content_type or "application/octet-stream"

        async def _stream(f: UploadFile = file) -> None:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                yield chunk

        try:
            await nc.upload_stream(nc_path, _stream(), content_type=mime)
            size = file.size or 0
            uploaded.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=size, success=True))
            await audit.log(
                db=db, user_id=user.id, event_type="files.file_uploaded",
                metadata={"folder_id": str(folder.id), "nc_path": nc_path, "size": size},
            )
        except NextcloudError as e:
            failed.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=0, success=False, error=str(e)))

    return UploadResult(uploaded=uploaded, failed=failed)


# ── Download file ──────────────────────────────────────────────────────────────

@router.get("/files/download", dependencies=[ModuleCheck])
async def download_file(
    folder_id: uuid.UUID,
    file_path: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> StreamingResponse:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "viewer", db, redis)

    nc = get_nc_service()
    try:
        response, client = await nc.download_stream(file_path)
    except NextcloudError as e:
        raise HTTPException(status_code=e.status if e.status in (404, 403) else 502, detail=str(e))

    filename = file_path.rsplit("/", 1)[-1]
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    encoded_filename = urlquote(filename, safe="")
    content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    async def _generator():
        try:
            async for chunk in response.aiter_bytes(65536):
                yield chunk
        finally:
            await client.aclose()

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_downloaded",
        metadata={"nc_path": file_path},
    )
    return StreamingResponse(
        _generator(),
        media_type=content_type,
        headers={"Content-Disposition": content_disposition},
    )


# ── Delete file ────────────────────────────────────────────────────────────────

@router.delete("/files/file", status_code=204, dependencies=[ModuleCheck])
async def delete_file(
    folder_id: uuid.UUID,
    file_path: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    nc = get_nc_service()
    try:
        await nc.delete(file_path)
    except NextcloudError as e:
        if e.status != 404:
            raise HTTPException(status_code=502, detail=str(e))

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_deleted",
        metadata={"nc_path": file_path},
    )


# ── Open in Collabora ──────────────────────────────────────────────────────────

@router.post("/files/open", response_model=FileOpenResponse, dependencies=[ModuleCheck])
async def open_in_collabora(
    folder_id: uuid.UUID,
    file_path: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileOpenResponse:
    folder = await _get_folder_or_404(db, folder_id)
    perm = await resolve_folder_permission(user, folder, db, redis)
    if not perm_gte(perm, "viewer"):
        raise HTTPException(status_code=403, detail="Insufficient file permissions")

    nc = get_nc_service()
    display_name = getattr(user, "display_name", None) or getattr(user, "full_name", None) or user.email

    from app.api.system_settings import load_system_settings
    from app.core.config import get_settings as _get_settings
    portal_base_url = load_system_settings().portal_base_url or _get_settings().portal_base_url
    avatar = getattr(user, "avatar_url", None) or ""

    try:
        if portal_base_url:
            data = await nc.get_collabora_url_via_federation(
                file_nc_path=file_path,
                portal_base_url=portal_base_url,
                redis=redis,
                user_id=str(user.id),
                display_name=display_name,
                avatar=avatar,
            )
        else:
            data = await nc.get_collabora_url(file_path, display_name)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=f"Collabora error: {e}")

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_opened_collabora",
        metadata={"nc_path": file_path},
    )
    return FileOpenResponse(type="collabora", url=data["url"], display_name=display_name)


# ── Permissions CRUD ───────────────────────────────────────────────────────────

@router.get(
    "/files/folders/{folder_id}/permissions",
    response_model=PermissionList,
    dependencies=[ModuleCheck],
)
async def list_permissions(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> PermissionList:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)
    res = await db.execute(
        select(FileFolderPermission).where(FileFolderPermission.folder_id == folder_id)
    )
    perms = res.scalars().all()
    return PermissionList(items=[PermissionPublic.model_validate(p) for p in perms])


@router.post(
    "/files/folders/{folder_id}/permissions",
    response_model=PermissionPublic,
    status_code=201,
    dependencies=[ModuleCheck],
)
async def grant_permission(
    folder_id: uuid.UUID,
    body: GrantPermissionRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> PermissionPublic:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    existing = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.folder_id == folder_id,
            FileFolderPermission.subject_id == body.subject_id,
        )
    )
    perm_row = existing.scalar_one_or_none()
    if perm_row:
        perm_row.permission = body.permission
        perm_row.subject_name = body.subject_name
        perm_row.granted_by = user.id
    else:
        perm_row = FileFolderPermission(
            folder_id=folder_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            subject_name=body.subject_name,
            permission=body.permission,
            granted_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(perm_row)

    await db.commit()
    await db.refresh(perm_row)
    await invalidate_folder_cache(redis, folder_id, db)
    return PermissionPublic.model_validate(perm_row)


@router.delete(
    "/files/folders/{folder_id}/permissions/{perm_id}",
    status_code=204,
    dependencies=[ModuleCheck],
)
async def revoke_permission(
    folder_id: uuid.UUID,
    perm_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "manager", db, redis)

    res = await db.execute(
        select(FileFolderPermission).where(
            FileFolderPermission.id == perm_id,
            FileFolderPermission.folder_id == folder_id,
        )
    )
    perm_row = res.scalar_one_or_none()
    if not perm_row:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.delete(perm_row)
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
