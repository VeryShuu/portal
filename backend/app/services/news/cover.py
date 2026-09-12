"""Загрузка / удаление обложки новости + responsive-варианты."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ALLOWED_NEWS_COVER_IMG_TYPES
from app.core.system_config import load_system_settings
from app.core.uploads import safe_join_within, stream_upload_to_segments
from app.models.news import News

from ._helpers import (
    _CONTENT_TYPE_TO_EXT,
    _NEWS_MEDIA_DIR,
    _build_cover_variants,
    _remove_cover_variants,
)


async def upload_cover(
    db: AsyncSession,
    news: News,
    file: UploadFile,
) -> News:
    """Validate, stream and persist a cover image for the given news item."""
    if file.content_type not in ALLOWED_NEWS_COVER_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image type. Use JPEG, PNG, WebP or GIF",
        )
    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    cover_name = f"cover.{ext}"
    max_bytes = load_system_settings().news_attachment_max_size_mb * 1024 * 1024
    await stream_upload_to_segments(
        file,
        _NEWS_MEDIA_DIR,
        (str(news.id), cover_name),
        max_size=max_bytes,
        allowed_mimes=ALLOWED_NEWS_COVER_IMG_TYPES,
    )
    # Путь восстановлен из тех же доверенных сегментов через признанный CodeQL
    # py/path-injection guard — нужен для _build_cover_variants ниже.
    file_path = safe_join_within(_NEWS_MEDIA_DIR, str(news.id), cover_name)
    relative_path = f"{news.id}/{cover_name}"
    out_dir = _NEWS_MEDIA_DIR / str(news.id)
    _remove_cover_variants(out_dir)
    import asyncio as _asyncio

    widths, dominant = await _asyncio.to_thread(_build_cover_variants, file_path, out_dir)
    await db.execute(
        update(News)
        .where(News.id == news.id)
        .values(
            cover_image=relative_path,
            cover_dominant_color=dominant,
            cover_variants=widths or None,
            updated_at=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(news)
    return news


async def delete_cover(db: AsyncSession, news: News) -> News:
    """Remove cover image file and clear the DB field."""
    if news.cover_image:
        cover_path = _NEWS_MEDIA_DIR / news.cover_image
        cover_path.unlink(missing_ok=True)
        news_dir = _NEWS_MEDIA_DIR / str(news.id)
        _remove_cover_variants(news_dir)
        if news_dir.exists() and not any(news_dir.iterdir()):
            news_dir.rmdir()
    await db.execute(
        update(News)
        .where(News.id == news.id)
        .values(
            cover_image=None,
            cover_dominant_color=None,
            cover_variants=None,
            updated_at=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(news)
    return news
