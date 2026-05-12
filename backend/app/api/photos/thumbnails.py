"""Thumbnail serving and on-demand generation; original file serving."""

from __future__ import annotations

import asyncio
import re
import uuid
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

_THUMB_SIZES = {200, 400, 600, 1000, 1600}


def _content_disposition(photo: Photo, *, download: bool) -> str:
    disp = "attachment" if download else "inline"
    safe_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", photo.original_name or photo.filename)
    encoded = _q(photo.original_name or photo.filename, safe="")
    return f"{disp}; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


def _serve_original_response(photo: Photo, folder: PhotoFolder, *, download: bool) -> Response:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", photo.filename)
    fs_path = folder.fs_path or folder.path or ""
    encoded_path = _q(fs_path, safe="/")
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
    res = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = res.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    await require_photo_permission(user, photo, PERM_VIEWER, db, redis)

    thumb_fs = photos_storage.thumb_path(photo_id, size)
    if not thumb_fs.exists():
        folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        if folder:
            original_path = (
                photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
            )
            if original_path.exists():
                try:
                    await asyncio.to_thread(
                        photos_storage.generate_thumbnails, photo_id, original_path
                    )
                    if not photo.processed:
                        await db.execute(
                            update(Photo).where(Photo.id == photo_id).values(processed=True)
                        )
                        await db.commit()
                except Exception as exc:
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
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    return _serve_original_response(photo, folder, download=download)
