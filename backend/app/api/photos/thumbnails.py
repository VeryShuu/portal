"""Thumbnail serving and on-demand generation; original file serving."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote as _q

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import PERM_VIEWER
from app.models.photos import Photo, PhotoFolder
from app.services import photos_storage
from app.services.photos_acl import require_photo_permission

from ._common import logger

router = APIRouter()

_THUMB_SIZES = set(photos_storage.THUMB_SIZES)


def _content_disposition(photo: Photo, *, download: bool) -> str:
    disp = "attachment" if download else "inline"
    safe_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", photo.original_name or photo.filename)
    encoded = _q(photo.original_name or photo.filename, safe="")
    return f"{disp}; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


def _serve_original_response(photo: Photo, folder: PhotoFolder, *, download: bool) -> Response:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", photo.filename)
    fs_path = folder.fs_path or folder.path or ""
    storage_kind = getattr(folder, "storage_kind", None) or "originals"

    if storage_kind == "import":
        try:
            abs_path = Path(fs_path).resolve()
            rel = abs_path.relative_to(photos_storage.IMPORT_ROOT.resolve())
            rel_str = "" if str(rel) == "." else str(rel)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail="Original missing") from exc
        encoded_path = _q(rel_str, safe="/")
        internal = (
            f"/internal/photos-import/{encoded_path}/{safe_name}"
            if encoded_path
            else f"/internal/photos-import/{safe_name}"
        )
    else:
        rel_fs = fs_path.lstrip("/")
        encoded_path = _q(rel_fs, safe="/")
        internal = (
            f"/internal/photos-originals/{encoded_path}/{safe_name}"
            if encoded_path
            else f"/internal/photos-originals/{safe_name}"
        )

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal,
            "Content-Type": photo.mime_type or "application/octet-stream",
            "Content-Disposition": _content_disposition(photo, download=download),
        },
    )


@router.get("/thumbnail/{photo_id}/{size}")
async def get_thumbnail(
    photo_id: uuid.UUID,
    size: int,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Photo not found")

    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)

    thumb_fs = photos_storage.thumb_path(photo_id, size)
    if not thumb_fs.exists():
        original_path = (
            photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
        )
        if original_path.exists():
            try:
                await photos_storage.generate_thumbnails_safe(photo_id, original_path)
                if not photo.processed:
                    await db.execute(
                        update(Photo).where(Photo.id == photo_id).values(processed=True)
                    )
                    await db.commit()
            except Exception as exc:
                from PIL.Image import DecompressionBombError
                if isinstance(exc, DecompressionBombError):
                    raise HTTPException(
                        status_code=400, detail="Image pixel count exceeds the allowed limit"
                    ) from exc
                logger.exception(
                    "photos.thumbnail.fallback_failed",
                    photo_id=str(photo_id),
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=500, detail="Thumbnail generation failed"
                ) from exc
        else:
            raise HTTPException(status_code=404, detail="Original missing")

    if format == "avif":
        avif_fs = photos_storage.thumb_avif_path(photo_id, size)
        if avif_fs.exists():
            return Response(
                status_code=200,
                headers={
                    "X-Accel-Redirect": f"/internal/photos-thumbs/{photo_id}/{size}.avif",
                    "Content-Type": "image/avif",
                    "Cache-Control": "public, max-age=3600",
                },
            )

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/internal/photos-thumbs/{photo_id}/{size}.webp",
            "Content-Type": "image/webp",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/original/{photo_id}")
async def get_original(
    photo_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    download: bool = Query(default=False),
) -> Response:
    res = await db.execute(select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None)))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder missing")
    return _serve_original_response(photo, folder, download=download)
