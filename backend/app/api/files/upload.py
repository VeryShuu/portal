"""File upload endpoint and Collabora open."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.files import repo
from app.core.constants import IDEMPOTENCY_TTL as _IDEMPOTENCY_TTL
from app.core.system_config import load_system_settings
from app.models.files import FileItem
from app.schemas.files import (
    FileOpenResponse,
    UploadResult,
    UploadResultItem,
)
from app.services.audit import make_audit_emitter
from app.services.files_acl import (
    perm_gte,
    require_file_access,
    require_folder_permission,
)
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import (
    _BLOCKED_UPLOAD_MIME,
    _UPLOAD_MIME_ALLOWLIST,
    ModuleCheck,
    _get_folder_or_404,
    sanitize_name,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.files import FileFolder
    from app.models.user import User
    from app.services.nextcloud.service import NextcloudService

router = APIRouter(tags=["files"])

_emit_file = make_audit_emitter("file")
_emit_folder = make_audit_emitter("folder")


def _failed_item(name: str, nc_path: str, error: str) -> UploadResultItem:
    """Build a failed UploadResultItem (size_bytes always 0)."""
    return UploadResultItem(name=name, nc_path=nc_path, size_bytes=0, success=False, error=error)


async def _process_one_upload(
    file: UploadFile,
    folder: FileFolder,
    max_size_bytes: int,
    nc: NextcloudService,
    db: AsyncSession,
    user: User,
) -> UploadResultItem:
    """Validate, stream-upload and upsert a single file. Returns success or failure item."""
    try:
        raw_name = file.filename or "unnamed"
        filename = sanitize_name(raw_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    except HTTPException as e:
        return _failed_item(file.filename or "unnamed", "", e.detail)

    nc_path = f"{folder.nc_path}/{filename}"

    header_size = file.size or 0
    if header_size and header_size > max_size_bytes:
        return _failed_item(filename, nc_path, "File exceeds maximum allowed size")

    header = await file.read(4096)
    if not header:
        return _failed_item(filename, nc_path, "Empty file")

    import magic

    detected_mime = magic.from_buffer(header, mime=True)
    if detected_mime in _BLOCKED_UPLOAD_MIME or detected_mime not in _UPLOAD_MIME_ALLOWLIST:
        return _failed_item(filename, nc_path, f"File type not allowed: {detected_mime}")
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
        # Перезалив существующего имени = тот же файл в NC (PUT перезаписал).
        # Обновляем имеющуюся запись, а не плодим дубли FileItem (иначе
        # delete_file через scalar_one_or_none падает с MultipleResultsFound).
        existing_item = await repo.find_active_file_item(db, folder_id=folder.id, name=filename)
        if existing_item is not None:
            existing_item.nc_path = nc_path
            existing_item.size_bytes = size
            existing_item.mime_type = detected_mime
            existing_item.uploaded_by = user.id
            existing_item.uploaded_at = now
        else:
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
        return UploadResultItem(name=filename, nc_path=nc_path, size_bytes=size, success=True)
    except (NextcloudError, HTTPException) as e:
        return _failed_item(
            filename, nc_path, str(e.detail) if isinstance(e, HTTPException) else str(e)
        )


async def _finalize_commit(
    db: AsyncSession,
    redis: Redis,
    folder: FileFolder,
    user: User,
    uploaded: list[UploadResultItem],
    failed: list[UploadResultItem],
) -> list[UploadResultItem]:
    """Commit the batch in one shot; on failure emit drift audit and demote to failed.

    Returns the resulting ``uploaded`` list (empty on commit failure).
    """
    from ._common import logger

    if not uploaded:
        return uploaded
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
        await _emit_folder(
            redis,
            event_type="files.upload_db_commit_drift",
            user_id=str(user.id),
            user_email=user.email,
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
        return []
    for u in uploaded:
        await _emit_file(
            redis,
            event_type="files.file_uploaded",
            user_id=str(user.id),
            user_email=user.email,
            resource_title=u.name,
            metadata={"folder_id": str(folder.id), "size": u.size_bytes},
        )
    return uploaded


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
            return cast(UploadResult, UploadResult.model_validate_json(cached))

    folder = await _get_folder_or_404(db, folder_id)
    await require_folder_permission(user, folder, "editor", db, redis)

    max_size_bytes = load_system_settings().max_upload_size_mb * 1024 * 1024

    nc = get_nc_service()
    uploaded: list[UploadResultItem] = []
    failed: list[UploadResultItem] = []

    for file in files:
        item = await _process_one_upload(file, folder, max_size_bytes, nc, db, user)
        (uploaded if item.success else failed).append(item)

    # 1.3: один commit на всю группу (вместо commit на каждый файл).
    # При сбое — drift-аудит, uploaded → failed; NC-файлы остаются осиротевшими
    # (sync устранит).
    uploaded = await _finalize_commit(db, redis, folder, user, uploaded, failed)

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
    safe_filename = sanitize_name(filename)
    perm = await require_file_access(user, folder, safe_filename, "viewer", db, redis)

    can_write = perm_gte(perm, "editor")

    nc_path = f"{folder.nc_path}/{safe_filename}"

    nc = get_nc_service()
    display_name = (
        getattr(user, "display_name", None) or getattr(user, "full_name", None) or user.email
    )

    portal_base_url = load_system_settings().portal_base_url
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
                can_write=can_write,
            )
        else:
            data = await nc.get_collabora_url(nc_path, display_name, can_write=can_write)
    except NextcloudError as e:
        raise HTTPException(status_code=502, detail=f"Collabora error: {e}") from e

    await _emit_file(
        redis,
        event_type="files.file_opened_collabora",
        user_id=str(user.id),
        user_email=user.email,
        resource_title=safe_filename,
        metadata={"folder_id": str(folder.id), "can_write": can_write},
    )
    return FileOpenResponse(
        type="collabora",
        url=data["url"],
        display_name=display_name,
        can_write=can_write,
    )
