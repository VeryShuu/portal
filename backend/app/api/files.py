"""Files module router — Phase 5 (ADR-032).

All operations go through portal-svc service account.
ACL is enforced via files_acl.py (viewer/editor/manager).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote as urlquote

import magic
from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep, RedisDep, require_role
from app.api.modules import load_modules
from app.core.config import get_settings
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
    invalidate_folder_cache,
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.nextcloud import NextcloudError, get_nc_service

logger = get_logger(__name__)

router = APIRouter(tags=["files"])

_SAFE_NAME_RE = re.compile(r'^[^\x00-\x1f\x7f/\\:*?"<>|]{1,200}$')
_PREVIEW_MIME_WHITELIST = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif",
    "application/pdf",
})

_BLOCKED_UPLOAD_MIME = frozenset({
    "text/html", "application/xhtml+xml",
    "image/svg+xml",
    "text/javascript", "application/javascript", "application/x-javascript",
    "application/x-sh", "application/x-csh", "text/x-shellscript",
    "application/x-executable", "application/x-elf",
    "application/x-msdos-program", "application/x-msdownload",
    "application/x-dosexec", "application/vnd.microsoft.portable-executable",
    "application/x-python-code", "text/x-python",
    "application/x-ruby",
    "application/x-php",
    "application/x-httpd-php",
})
_IDEMPOTENCY_TTL = 86400


def sanitize_name(name: str) -> str:
    name = name.strip().strip(".")
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty")
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="Name contains invalid characters. Use printable characters only, no / \\ : * ? \" < > |",
        )
    if name in ("..", "."):
        raise HTTPException(status_code=422, detail="Name must not be '.' or '..'")
    return name


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
        select(FileFolder).where(FileFolder.deleted_at.is_(None)).order_by(FileFolder.name)
    )
    all_folders = res.scalars().all()

    accessible: dict[uuid.UUID, str] = {}
    for f in all_folders:
        perm = await resolve_folder_permission(user, f, db, redis)
        if perm and perm_gte(perm, "viewer"):
            accessible[f.id] = perm

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
            children=children,
        )

    nodes = [build_node(f) for f in all_folders if f.parent_id == parent_id and f.id in accessible]
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
    nc_error = False
    try:
        items = await nc.list_folder(folder.nc_path)
    except NextcloudError as e:
        logger.warning("nc.list_folder_failed", path=folder.nc_path, status=e.status)
        items = []
        nc_error = True

    breadcrumbs = await _build_breadcrumbs(folder, db, user, redis)

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

    renamed = False
    old_nc_path = folder.nc_path
    if body.name is not None and body.name != folder.name:
        safe_name = sanitize_name(body.name)
        parent_path = old_nc_path.rsplit("/", 1)[0] if "/" in old_nc_path else ""
        new_nc_path = f"{parent_path}/{safe_name}".lstrip("/") if parent_path else safe_name

        nc = get_nc_service()
        try:
            await nc.move(old_nc_path, new_nc_path)
        except NextcloudError as e:
            raise HTTPException(status_code=502, detail=f"Nextcloud error: {e}")

        folder.nc_path = new_nc_path
        folder.name = body.name
        renamed = True

    if body.description is not None:
        folder.description = body.description

    folder.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except Exception:
        if renamed:
            nc = get_nc_service()
            try:
                await nc.move(folder.nc_path, old_nc_path)
            except Exception as rollback_exc:
                logger.error(
                    "files.rename_db_commit_failed_nc_rollback_failed",
                    old_nc_path=old_nc_path,
                    new_nc_path=folder.nc_path,
                    error=str(rollback_exc),
                )
        raise

    await db.refresh(folder)
    await invalidate_folder_cache(redis, folder.id, db)

    if renamed:
        await audit.log(
            db=db, user_id=user.id, event_type="files.folder_renamed",
            metadata={"folder_id": str(folder.id), "old_nc_path": old_nc_path, "new_nc_path": folder.nc_path},
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
    dependencies=[ModuleCheck, Depends(RateLimiter(times=20, minutes=1))],
)
async def upload_files(
    folder_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    files: list[UploadFile],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> UploadResult:
    if idempotency_key:
        cached = await redis.get(f"idem:upload:{idempotency_key}")
        if cached:
            return UploadResult.model_validate_json(cached)

    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    settings = get_settings()
    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024

    nc = get_nc_service()
    uploaded: list[UploadResultItem] = []
    failed: list[UploadResultItem] = []

    for file in files:
        try:
            raw_name = file.filename or "unnamed"
            filename = sanitize_name(raw_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        except HTTPException as e:
            failed.append(UploadResultItem(name=file.filename or "unnamed", nc_path="", size_bytes=0, success=False, error=e.detail))
            continue

        nc_path = f"{folder.nc_path}/{filename}"

        header_size = file.size or 0
        if header_size and header_size > max_size_bytes:
            failed.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=0, success=False, error="File exceeds maximum allowed size"))
            continue

        header = await file.read(4096)
        if not header:
            failed.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=0, success=False, error="Empty file"))
            continue

        detected_mime = magic.from_buffer(header, mime=True)
        if detected_mime in _BLOCKED_UPLOAD_MIME:
            failed.append(UploadResultItem(
                name=filename, nc_path=nc_path, size_bytes=0, success=False,
                error=f"File type not allowed: {detected_mime}",
            ))
            continue
        await file.seek(0)

        async def _stream(f: UploadFile = file, limit: int = max_size_bytes) -> None:
            total = 0
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="File exceeds maximum allowed size")
                yield chunk

        try:
            await nc.upload_stream(nc_path, _stream(), content_type=detected_mime)
            size = file.size or 0
            uploaded.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=size, success=True))
            await audit.log(
                db=db, user_id=user.id, event_type="files.file_uploaded",
                metadata={"folder_id": str(folder.id), "filename": filename, "size": size},
            )
        except NextcloudError as e:
            failed.append(UploadResultItem(name=filename, nc_path=nc_path, size_bytes=0, success=False, error=str(e)))

    result = UploadResult(uploaded=uploaded, failed=failed)
    if idempotency_key:
        await redis.set(f"idem:upload:{idempotency_key}", result.model_dump_json(), ex=_IDEMPOTENCY_TTL)
    return result


# ── Download file ──────────────────────────────────────────────────────────────

@router.get("/files/download", dependencies=[ModuleCheck, Depends(RateLimiter(times=60, minutes=1))])
async def download_file(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> StreamingResponse:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "viewer", db, redis)

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    try:
        response, client = await nc.download_stream(nc_path)
    except NextcloudError as e:
        raise HTTPException(status_code=e.status if e.status in (404, 403) else 502, detail=str(e))

    encoded_filename = urlquote(safe_filename, safe="")
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    async def _generator():
        try:
            async for chunk in response.aiter_bytes(65536):
                yield chunk
        finally:
            await client.aclose()

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_downloaded",
        metadata={"folder_id": str(folder.id), "filename": safe_filename},
    )
    return StreamingResponse(
        _generator(),
        media_type=content_type,
        headers={"Content-Disposition": content_disposition},
    )


# ── Preview file (inline) ──────────────────────────────────────────────────────

@router.get("/files/preview", dependencies=[ModuleCheck, Depends(RateLimiter(times=60, minutes=1))])
async def preview_file(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> StreamingResponse:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "viewer", db, redis)

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    try:
        response, client = await nc.download_stream(nc_path)
    except NextcloudError as e:
        raise HTTPException(status_code=e.status if e.status in (404, 403) else 502, detail=str(e))

    content_type = response.headers.get("Content-Type", "application/octet-stream")
    mime_base = content_type.split(";")[0].strip().lower()

    if mime_base not in _PREVIEW_MIME_WHITELIST:
        await client.aclose()
        raise HTTPException(status_code=415, detail="Preview not available for this file type")

    encoded_filename = urlquote(safe_filename, safe="")
    content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

    async def _generator():
        try:
            async for chunk in response.aiter_bytes(65536):
                yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        _generator(),
        media_type=content_type,
        headers={
            "Content-Disposition": content_disposition,
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── Delete file ────────────────────────────────────────────────────────────────

@router.delete("/files/file", status_code=204, dependencies=[ModuleCheck])
async def delete_file(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> None:
    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    try:
        await nc.delete(nc_path)
    except NextcloudError as e:
        if e.status != 404:
            raise HTTPException(status_code=502, detail=str(e))

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_deleted",
        metadata={"folder_id": str(folder.id), "filename": safe_filename},
    )


# ── Open in Collabora ──────────────────────────────────────────────────────────

@router.post("/files/open", response_model=FileOpenResponse, dependencies=[ModuleCheck])
async def open_in_collabora(
    folder_id: uuid.UUID,
    filename: str,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FileOpenResponse:
    folder = await _get_folder_or_404(db, folder_id)
    perm = await resolve_folder_permission(user, folder, db, redis)
    if not perm_gte(perm, "viewer"):
        raise HTTPException(status_code=403, detail="Insufficient file permissions")

    safe_filename = sanitize_name(filename)
    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    display_name = getattr(user, "display_name", None) or getattr(user, "full_name", None) or user.email

    from app.api.system_settings import load_system_settings
    portal_base_url = load_system_settings().portal_base_url or get_settings().portal_base_url
    avatar = getattr(user, "avatar_url", None) or ""

    try:
        if portal_base_url:
            data = await nc.get_collabora_url_via_federation(
                file_nc_path=nc_path,
                portal_base_url=portal_base_url,
                redis=redis,
                user_id=str(user.id),
                display_name=display_name,
                avatar=avatar,
            )
        else:
            data = await nc.get_collabora_url(nc_path, display_name)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=f"Collabora error: {e}")

    await audit.log(
        db=db, user_id=user.id, event_type="files.file_opened_collabora",
        metadata={"folder_id": str(folder.id), "filename": safe_filename},
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

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        res2 = await db.execute(
            select(FileFolderPermission).where(
                FileFolderPermission.folder_id == folder_id,
                FileFolderPermission.subject_id == body.subject_id,
            )
        )
        perm_row = res2.scalar_one_or_none()
        if perm_row is None:
            raise HTTPException(status_code=409, detail="Permission conflict, please retry")
        perm_row.permission = body.permission
        perm_row.subject_name = body.subject_name
        perm_row.granted_by = user.id
        await db.commit()
    await db.refresh(perm_row)
    await invalidate_folder_cache(redis, folder_id, db)
    await audit.log(
        db=db, user_id=user.id, event_type="files.permission_granted",
        metadata={"folder_id": str(folder_id), "subject_id": body.subject_id, "permission": body.permission},
    )
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

    subject_id = perm_row.subject_id
    await db.delete(perm_row)
    await db.commit()
    await invalidate_folder_cache(redis, folder_id, db)
    await audit.log(
        db=db, user_id=user.id, event_type="files.permission_revoked",
        metadata={"folder_id": str(folder_id), "perm_id": str(perm_id), "subject_id": subject_id},
    )
