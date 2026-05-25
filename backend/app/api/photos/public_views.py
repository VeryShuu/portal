"""Анонимные публичные эндпойнты просмотра по share-токенам.

Выделено из ``sharing.py`` (см. ревью, находка #4: разделение
ответственностей — здесь только read-only выдача по токену, без
управления самими токенами).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbDep
from app.models.photos import (
    Photo,
    PhotoFolder,
    PhotoFolderShareToken,
    PhotoShareToken,
)
from app.schemas.photos import (
    PhotoListAnon,
    PhotoPublicAnon,
)
from app.services import photos_storage
from app.services.photos_serializers import photo_to_public_anon

from ._common import _xaccel_thumb_response

router = APIRouter()

_THUMB_SIZES = set(photos_storage.THUMB_SIZES)


def _resolve_folder_token_sync_check(token_row: PhotoFolderShareToken) -> None:
    now = datetime.now(UTC)
    if token_row.revoked_at is not None or (
        token_row.expires_at is not None and token_row.expires_at < now
    ):
        raise HTTPException(status_code=410, detail="Share link expired or revoked")


async def _resolve_token(db: AsyncSession, token: str) -> tuple[Photo, PhotoFolder]:
    res = await db.execute(select(PhotoShareToken).where(PhotoShareToken.token == token))
    link = res.scalar_one_or_none()
    if not link or link.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.expires_at is not None and link.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Link expired")
    res2 = await db.execute(
        select(Photo).where(Photo.id == link.photo_id, Photo.deleted_at.is_(None))
    )
    photo = res2.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    folder = await db.scalar(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder missing")
    return photo, folder


def _thumb_response(photo_id: uuid.UUID, size: int, fmt: str) -> Response:
    """Выдача thumbnail по token-эндпойнтам (тонкая обёртка над #B-1 helper)."""
    resp = _xaccel_thumb_response(photo_id, size, fmt)
    if resp is None:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return resp


@router.get("/public-folder/{token}/info")
async def public_folder_info(token: str, db: DbDep) -> dict:
    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    folder = await db.scalar(
        select(PhotoFolder).where(
            PhotoFolder.id == tok_row.folder_id, PhotoFolder.deleted_at.is_(None)
        )
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    count = await db.scalar(
        select(func.count(Photo.id)).where(
            Photo.folder_id == folder.id,
            Photo.deleted_at.is_(None),
        )
    )
    return {
        "folder_name": folder.name,
        "photos_count": int(count or 0),
        "created_at": tok_row.created_at.isoformat(),
    }


@router.get("/public-folder/{token}/photos", response_model=PhotoListAnon)
async def public_folder_photos(
    token: str,
    db: DbDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> PhotoListAnon:
    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    base = select(Photo).where(
        Photo.folder_id == tok_row.folder_id,
        Photo.deleted_at.is_(None),
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    res = await db.execute(
        base.order_by(Photo.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return PhotoListAnon(
        items=[photo_to_public_anon(p) for p in res.scalars().all()],
        total=int(total or 0),
        page=page,
        per_page=per_page,
    )


@router.get(
    "/public-folder/{token}/thumbnail/{photo_id}/{size}",
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def public_folder_thumbnail(
    token: str,
    photo_id: uuid.UUID,
    size: int,
    db: DbDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid size")
    tok_row = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    if not tok_row:
        raise HTTPException(status_code=404, detail="Not found")
    _resolve_folder_token_sync_check(tok_row)
    photo = await db.scalar(
        select(Photo).where(
            Photo.id == photo_id,
            Photo.folder_id == tok_row.folder_id,
            Photo.deleted_at.is_(None),
        )
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return _thumb_response(photo.id, size, format)


@router.get("/public/{token}/info", response_model=PhotoPublicAnon)
async def public_photo_info(token: str, db: DbDep) -> PhotoPublicAnon:
    photo, folder = await _resolve_token(db, token)
    return PhotoPublicAnon(
        id=photo.id,
        folder_path=folder.path,
        original_name=photo.original_name,
        size_bytes=photo.size_bytes,
        mime_type=photo.mime_type,
        width=photo.width,
        height=photo.height,
        taken_at=photo.taken_at,
        description=photo.description,
        processed=photo.processed,
        blurhash=getattr(photo, "blurhash", None),
        created_at=photo.created_at,
    )


@router.get(
    "/public/{token}/thumbnail/{size}",
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def public_thumbnail(
    token: str,
    size: int,
    db: DbDep,
    format: str = Query(default="webp", pattern="^(webp|avif)$"),
) -> Response:
    if size not in _THUMB_SIZES:
        raise HTTPException(status_code=400, detail="Invalid thumbnail size")
    photo, _folder = await _resolve_token(db, token)
    return _thumb_response(photo.id, size, format)


@router.get("/public/{token}/file")
async def public_original(
    token: str,
    db: DbDep,
    download: bool = Query(default=False),
) -> Response:
    from .thumbnails import _serve_original_response

    photo, folder = await _resolve_token(db, token)
    return _serve_original_response(photo, folder, download=download)
