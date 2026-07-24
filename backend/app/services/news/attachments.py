"""Загрузка / удаление произвольных вложений к новости."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.system_config import load_system_settings
from app.core.uploads import safe_join_within, stream_upload_to_path
from app.models.news import News, NewsAttachment

from ._helpers import _NEWS_MEDIA_DIR


async def upload_attachment(
    db: AsyncSession,
    news: News,
    file: UploadFile,
) -> NewsAttachment:
    """Stream and persist an attachment (any MIME type)."""
    att_id = uuid.uuid4()
    dest = _NEWS_MEDIA_DIR / str(news.id) / "attachments" / str(att_id)
    max_bytes = load_system_settings().news_attachment_max_size_mb * 1024 * 1024
    written, detected_mime = await stream_upload_to_path(
        file, dest, max_size=max_bytes, allowed_mimes=None
    )
    att = NewsAttachment(
        id=att_id,
        news_id=news.id,
        filename=str(att_id),
        original_name=file.filename or str(att_id),
        mime_type=detected_mime or file.content_type,
        file_size=written,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


async def delete_attachment(
    db: AsyncSession,
    news_id: uuid.UUID,
    att_id: uuid.UUID,
) -> NewsAttachment:
    """Delete attachment file and remove the DB row. Returns the deleted row."""
    result = await db.execute(
        select(NewsAttachment).where(NewsAttachment.id == att_id, NewsAttachment.news_id == news_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    path = safe_join_within(_NEWS_MEDIA_DIR, str(news_id), "attachments", att.filename)
    path.unlink(missing_ok=True)
    await db.execute(delete(NewsAttachment).where(NewsAttachment.id == att_id))
    await db.commit()
    return att
