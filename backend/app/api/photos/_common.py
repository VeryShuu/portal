"""Shared helpers for the photos API sub-package."""

from __future__ import annotations

import re
import unicodedata
import uuid

from arq import ArqRedis
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.responses import Response

from app.api.modules import load_modules
from app.core.logging import get_logger
from app.core.modules_config import PhotosModuleSettings
from app.models.photos import PhotoFolder
from app.services import photos_storage
from app.services.photos_serializers import (
    folder_to_public as _folder_to_public,
)
from app.services.photos_serializers import (
    photo_to_public as _photo_to_public,
)
from app.services.photos_serializers import (
    photo_to_public_anon as _photo_to_public_anon,
)
from app.services.photos_serializers import (
    zip_job_to_public as _zip_job_to_public,
)

logger = get_logger(__name__)


def _slugify(text_: str) -> str:
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def _get_arq(request: Request) -> ArqRedis | None:
    return getattr(request.app.state, "arq_pool", None)


async def _enqueue_processing(request: Request, photo_id: uuid.UUID) -> None:
    pool = await _get_arq(request)
    if pool is None:
        return
    try:
        await pool.enqueue_job(
            "process_photo_upload",
            str(photo_id),
            _job_id=f"photos:process:{photo_id}",
        )
    except Exception as exc:
        logger.warning("photos.enqueue_failed", photo_id=str(photo_id), error=str(exc))


def _module_settings() -> PhotosModuleSettings:
    return load_modules().photos


async def _would_create_cycle(
    db: AsyncSession, folder_id: uuid.UUID, new_parent_id: uuid.UUID | None
) -> bool:
    """Возвращает True если перемещение папки под new_parent_id создаст цикл."""
    if new_parent_id is None:
        return False
    if new_parent_id == folder_id:
        return True
    current: uuid.UUID | None = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current == folder_id:
            return True
        if current in visited:
            break
        visited.add(current)
        current = await db.scalar(select(PhotoFolder.parent_id).where(PhotoFolder.id == current))
    return False


_THUMB_XACCEL_CACHE_CONTROL = "public, max-age=3600"


def _xaccel_thumb_response(photo_id: uuid.UUID, size: int, fmt: str) -> Response | None:
    """Build an X-Accel-Redirect response for thumbnail file if present (#B-1).

    Returns ``Response(200)`` with `X-Accel-Redirect` header when the
    requested ``(photo_id, size, fmt)`` thumbnail exists on disk; returns
    ``None`` otherwise so the caller can decide the fallback (404/503/...).

    Shared between private (``thumbnails.py``) and public-share
    (``public_views.py``) endpoints.
    """
    if fmt == "avif":
        fs = photos_storage.thumb_avif_path(photo_id, size)
        ctype = "image/avif"
        ext = "avif"
    else:
        fs = photos_storage.thumb_path(photo_id, size)
        ctype = "image/webp"
        ext = "webp"
    if not fs.exists():
        return None
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo_id}/{size}.{ext}",
            "Content-Type": ctype,
            "Cache-Control": _THUMB_XACCEL_CACHE_CONTROL,
        },
    )


__all__ = [
    "_enqueue_processing",
    "_folder_to_public",
    "_get_arq",
    "_module_settings",
    "_photo_to_public",
    "_photo_to_public_anon",
    "_slugify",
    "_would_create_cycle",
    "_xaccel_thumb_response",
    "_zip_job_to_public",
    "logger",
]
