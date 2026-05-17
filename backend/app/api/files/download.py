"""Download and inline preview endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from urllib.parse import quote as urlquote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.services.audit import push_audit_event
from app.services.files_acl import require_folder_permission
from app.services.nextcloud import NextcloudError, get_nc_service

from ._common import (
    _PREVIEW_MIME_WHITELIST,
    ModuleCheck,
    _get_folder_or_404,
    sanitize_name,
)

router = APIRouter(tags=["files"])


@router.get(
    "/files/download", dependencies=[ModuleCheck, Depends(RateLimiter(times=60, minutes=1))]
)
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
        raise HTTPException(
            status_code=e.status if e.status in (404, 403) else 502,
            detail=str(e),
        ) from e

    encoded_filename = urlquote(safe_filename, safe="")
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"

    async def _generator() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in response.aiter_bytes(65536):
                yield chunk
        finally:
            await client.aclose()

    await push_audit_event(
        redis,
        event_type="files.file_downloaded",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="file",
        resource_title=safe_filename,
        metadata={"folder_id": str(folder.id)},
    )
    return StreamingResponse(
        _generator(),
        media_type=content_type,
        headers={"Content-Disposition": content_disposition},
    )


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
        raise HTTPException(
            status_code=e.status if e.status in (404, 403) else 502,
            detail=str(e),
        ) from e

    content_type = response.headers.get("Content-Type", "application/octet-stream")
    mime_base = content_type.split(";")[0].strip().lower()

    if mime_base not in _PREVIEW_MIME_WHITELIST:
        await client.aclose()
        raise HTTPException(status_code=415, detail="Preview not available for this file type")

    encoded_filename = urlquote(safe_filename, safe="")
    content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

    async def _generator() -> AsyncGenerator[bytes, None]:
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
