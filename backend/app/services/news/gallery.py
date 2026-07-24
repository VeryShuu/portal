"""Загрузка / удаление изображений галереи новости."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ALLOWED_NEWS_COVER_IMG_TYPES
from app.core.system_config import load_system_settings
from app.core.uploads import safe_join_within, stream_upload_to_path
from app.models.news import News, NewsGalleryImage

from ._helpers import _CONTENT_TYPE_TO_EXT, _NEWS_MEDIA_DIR


async def upload_gallery_image(
    db: AsyncSession,
    news: News,
    file: UploadFile,
) -> NewsGalleryImage:
    """Validate, stream and persist a gallery image."""
    if file.content_type not in ALLOWED_NEWS_COVER_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image type. Use JPEG, PNG, WebP or GIF",
        )
    img_id = uuid.uuid4()
    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    filename = f"{img_id}.{ext}"
    dest = _NEWS_MEDIA_DIR / str(news.id) / "gallery" / filename
    max_bytes = load_system_settings().news_attachment_max_size_mb * 1024 * 1024
    written, _detected = await stream_upload_to_path(
        file, dest, max_size=max_bytes, allowed_mimes=ALLOWED_NEWS_COVER_IMG_TYPES
    )
    next_order_subq = (
        select(func.coalesce(func.max(NewsGalleryImage.sort_order), -1) + 1)
        .where(NewsGalleryImage.news_id == news.id)
        .scalar_subquery()
    )
    stmt = (
        insert(NewsGalleryImage)
        .values(
            id=img_id,
            news_id=news.id,
            filename=filename,
            original_name=file.filename or filename,
            sort_order=next_order_subq,
            file_size=written,
        )
        .returning(NewsGalleryImage)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def delete_gallery_image(
    db: AsyncSession,
    news_id: uuid.UUID,
    img_id: uuid.UUID,
) -> NewsGalleryImage:
    """Delete gallery image file and remove the DB row. Returns the deleted row."""
    result = await db.execute(
        select(NewsGalleryImage).where(
            NewsGalleryImage.id == img_id, NewsGalleryImage.news_id == news_id
        )
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    safe_join_within(_NEWS_MEDIA_DIR, str(news_id), "gallery", img.filename).unlink(missing_ok=True)
    await db.execute(delete(NewsGalleryImage).where(NewsGalleryImage.id == img_id))
    await db.commit()
    return img
