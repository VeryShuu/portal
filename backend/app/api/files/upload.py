"""File upload endpoint and Collabora open."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.constants import IDEMPOTENCY_TTL as _IDEMPOTENCY_TTL
from app.core.system_config import load_system_settings
from app.models.files import FileItem
from app.schemas.files import (
    FileOpenResponse,
    UploadResult,
    UploadResultItem,
)
from app.services.audit import push_audit_event
from app.services.files_acl import (
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import (
    _BLOCKED_UPLOAD_MIME,
    _UPLOAD_MIME_ALLOWLIST,
    ModuleCheck,
    _get_folder_or_404,
    sanitize_name,
)

router = APIRouter(tags=["files"])


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
        cached = await redis.get(f"idem:upload:{user.id}:{idempotency_key}")
        if cached:
            return UploadResult.model_validate_json(cached)

    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    max_size_bytes = load_system_settings().max_upload_size_mb * 1024 * 1024

    nc = get_nc_service()
    uploaded: list[UploadResultItem] = []
    failed: list[UploadResultItem] = []

    from ._common import logger

    for file in files:
        try:
            raw_name = file.filename or "unnamed"
            filename = sanitize_name(raw_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        except HTTPException as e:
            failed.append(
                UploadResultItem(
                    name=file.filename or "unnamed",
                    nc_path="",
                    size_bytes=0,
                    success=False,
                    error=e.detail,
                )
            )
            continue

        nc_path = f"{folder.nc_path}/{filename}"

        header_size = file.size or 0
        if header_size and header_size > max_size_bytes:
            failed.append(
                UploadResultItem(
                    name=filename,
                    nc_path=nc_path,
                    size_bytes=0,
                    success=False,
                    error="File exceeds maximum allowed size",
                )
            )
            continue

        header = await file.read(4096)
        if not header:
            failed.append(
                UploadResultItem(
                    name=filename, nc_path=nc_path, size_bytes=0, success=False, error="Empty file"
                )
            )
            continue

        import magic

        detected_mime = magic.from_buffer(header, mime=True)
        if detected_mime in _BLOCKED_UPLOAD_MIME or detected_mime not in _UPLOAD_MIME_ALLOWLIST:
            failed.append(
                UploadResultItem(
                    name=filename,
                    nc_path=nc_path,
                    size_bytes=0,
                    success=False,
                    error=f"File type not allowed: {detected_mime}",
                )
            )
            continue
        await file.seek(0)

        async def _stream(
            f: UploadFile = file, limit: int = max_size_bytes
        ) -> AsyncGenerator[bytes, None]:
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
            now = datetime.now(UTC)
            db.add(
                FileItem(
                    folder_id=folder.id,
                    nc_path=nc_path,
                    name=filename,
                    size_bytes=size,
                    mime_type=detected_mime,
                    uploaded_by=user.id,
                    uploaded_at=now,
                )
            )
            uploaded.append(
                UploadResultItem(name=filename, nc_path=nc_path, size_bytes=size, success=True)
            )
        except (NextcloudError, HTTPException) as e:
            failed.append(
                UploadResultItem(
                    name=filename,
                    nc_path=nc_path,
                    size_bytes=0,
                    success=False,
                    error=str(e.detail) if isinstance(e, HTTPException) else str(e),
                )
            )

    # 1.3: один commit на всю группу (вместо commit на каждый файл).
    # При сбое — drift-аудит, uploaded → failed; NC-файлы остаются осиротевшими
    # (sync устранит).
    if uploaded:
        try:
            await db.commit()
        except Exception as commit_exc:
            await db.rollback()
            logger.error(
                "files.bulk_upload_db_commit_failed",
                folder_id=str(folder.id),
                count=len(uploaded),
                error=str(commit_exc),
            )
            await push_audit_event(
                redis,
                event_type="files.upload_db_commit_drift",
                user_id=str(user.id),
                resource_type="folder",
                resource_id=str(folder.id),
                metadata={
                    "folder_id": str(folder.id),
                    "orphaned_nc_paths": [u.nc_path for u in uploaded],
                },
            )
            for u in uploaded:
                failed.append(
                    UploadResultItem(
                        name=u.name,
                        nc_path=u.nc_path,
                        size_bytes=0,
                        success=False,
                        error="db_commit_failed",
                    )
                )
            uploaded = []
        else:
            for u in uploaded:
                await push_audit_event(
                    redis,
                    event_type="files.file_uploaded",
                    user_id=str(user.id),
                    resource_type="file",
                    resource_title=u.name,
                    metadata={"folder_id": str(folder.id), "size": u.size_bytes},
                )

    result = UploadResult(uploaded=uploaded, failed=failed)
    if idempotency_key:
        await redis.set(
            f"idem:upload:{user.id}:{idempotency_key}",
            result.model_dump_json(),
            ex=_IDEMPOTENCY_TTL,
        )
    return result


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
    display_name = (
        getattr(user, "display_name", None) or getattr(user, "full_name", None) or user.email
    )

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
        raise HTTPException(status_code=502, detail=f"Collabora error: {e}") from e

    await push_audit_event(
        redis,
        event_type="files.file_opened_collabora",
        user_id=str(user.id),
        resource_type="file",
        resource_title=safe_filename,
        metadata={"folder_id": str(folder.id)},
    )
    return FileOpenResponse(type="collabora", url=data["url"], display_name=display_name)
