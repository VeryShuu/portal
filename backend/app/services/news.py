"""News service — бизнес-логика."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ALLOWED_NEWS_COVER_IMG_TYPES
from app.core.logging import get_logger
from app.core.sanitize import sanitize_html
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_path
from app.models.news import News, NewsAttachment, NewsGalleryImage, NewsVersion
from app.models.user import User

_NEWS_MEDIA_DIR = Path("/data/news_media")

_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

logger = get_logger(__name__)


def _targeting_filter(stmt, user: User):
    """Фильтр по таргетингу: показывать новость, если ОБА условия:
    - target_departments пуст ИЛИ содержит отдел пользователя
    - target_roles пуст ИЛИ содержит роль пользователя (P0-11)
    """
    from sqlalchemy import String, cast, or_
    from sqlalchemy.dialects.postgresql import ARRAY

    dept_clause = or_(
        News.target_departments.is_(None),
        News.target_departments == [],
    )
    if user.department is not None:
        dept_clause = or_(
            dept_clause,
            News.target_departments.contains(cast([user.department], ARRAY(String))),
        )

    role_clause = or_(
        News.target_roles.is_(None),
        News.target_roles == [],
        News.target_roles.contains(cast([user.role], ARRAY(String))),
    )

    return stmt.where(dept_clause).where(role_clause)


async def get_news_list(
    db: AsyncSession,
    *,
    user: User,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    pinned_first: bool = True,
    category: str | None = None,
    is_pinned: bool | None = None,
    q: str | None = None,
) -> tuple[list[News], int]:
    stmt = select(News).where(News.deleted_at.is_(None))

    if status_filter:
        stmt = stmt.where(News.status == status_filter)
    elif user.role not in ("editor", "admin"):
        stmt = stmt.where(News.status == "published")

    if category is not None:
        from sqlalchemy import String, cast
        from sqlalchemy.dialects.postgresql import ARRAY
        stmt = stmt.where(News.categories.contains(cast([category], ARRAY(String))))

    if is_pinned is not None:
        stmt = stmt.where(News.is_pinned == is_pinned)

    if q:
        from sqlalchemy import or_
        pattern = f"%{q}%"
        stmt = stmt.where(or_(News.title.ilike(pattern), News.body.ilike(pattern)))

    if user.role not in ("editor", "admin"):
        stmt = _targeting_filter(stmt, user)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    if pinned_first:
        stmt = stmt.order_by(
            News.is_pinned.desc(),
            News.published_at.desc(),
            News.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(News.published_at.desc(), News.created_at.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_news_by_id(db: AsyncSession, news_id: uuid.UUID) -> News | None:
    result = await db.execute(select(News).where(News.id == news_id, News.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def create_news(db: AsyncSession, *, author: User, data: dict) -> News:
    now = datetime.now(UTC)
    # P0-2: sanitize HTML body before persisting (XSS prevention).
    body = sanitize_html(data.get("body", ""))
    news = News(
        title=data["title"],
        body=body,
        status=data.get("status", "draft"),
        is_pinned=data.get("is_pinned", False),
        categories=data.get("categories", []),
        target_departments=data.get("target_departments"),
        target_roles=data.get("target_roles"),
        publish_at=data.get("publish_at"),
        archive_at=data.get("archive_at"),
        cover_focal_point=data.get("cover_focal_point"),
        author_id=author.id,
        current_version=1,
    )
    if news.status == "published" and not news.published_at:
        news.published_at = now

    db.add(news)
    await db.flush()

    version = NewsVersion(
        news_id=news.id,
        version=1,
        title=news.title,
        body=news.body,
        editor_id=author.id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(news)
    return news


async def update_news(db: AsyncSession, *, news: News, editor: User, data: dict) -> News:
    now = datetime.now(UTC)
    changed = False

    for field in (
        "title",
        "body",
        "status",
        "is_pinned",
        "categories",
        "target_departments",
        "target_roles",
        "publish_at",
        "archive_at",
        "published_at",
        "cover_focal_point",
    ):
        if field in data and data[field] is not None:
            new_val = data[field]
            # P0-2: sanitize body on update too.
            if field == "body":
                new_val = sanitize_html(new_val)
            if getattr(news, field) != new_val:
                setattr(news, field, new_val)
                changed = True

    if data.get("status") == "published" and not news.published_at:
        news.published_at = now

    if changed:
        news.current_version += 1
        news.updated_at = now

        version = NewsVersion(
            news_id=news.id,
            version=news.current_version,
            title=news.title,
            body=news.body,
            editor_id=editor.id,
        )
        db.add(version)
        db.add(news)
        await db.commit()
        await db.refresh(news)
    return news


async def delete_news(db: AsyncSession, news: News) -> None:
    news.deleted_at = datetime.now(UTC)
    news.status = "archived"
    await db.commit()


async def get_news_versions(db: AsyncSession, news_id: uuid.UUID) -> list[NewsVersion]:
    result = await db.execute(
        select(NewsVersion)
        .where(NewsVersion.news_id == news_id)
        .order_by(NewsVersion.version.desc())
    )
    return list(result.scalars().all())


async def increment_view_count(db: AsyncSession, news_id: uuid.UUID) -> None:
    await db.execute(update(News).where(News.id == news_id).values(view_count=News.view_count + 1))
    await db.commit()


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
    file_path = _NEWS_MEDIA_DIR / str(news.id) / f"cover.{ext}"
    max_bytes = load_system_settings().news_attachment_max_size_mb * 1024 * 1024
    await stream_upload_to_path(
        file, file_path, max_size=max_bytes, allowed_mimes=ALLOWED_NEWS_COVER_IMG_TYPES
    )
    relative_path = f"{news.id}/cover.{ext}"
    await db.execute(update(News).where(News.id == news.id).values(cover_image=relative_path))
    await db.commit()
    await db.refresh(news)
    return news


async def delete_cover(db: AsyncSession, news: News) -> News:
    """Remove cover image file and clear the DB field."""
    if news.cover_image:
        cover_path = _NEWS_MEDIA_DIR / news.cover_image
        cover_path.unlink(missing_ok=True)
        news_dir = _NEWS_MEDIA_DIR / str(news.id)
        if news_dir.exists() and not any(news_dir.iterdir()):
            news_dir.rmdir()
    await db.execute(update(News).where(News.id == news.id).values(cover_image=None))
    await db.commit()
    await db.refresh(news)
    return news


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
    (_NEWS_MEDIA_DIR / str(news_id) / "gallery" / img.filename).unlink(missing_ok=True)
    await db.execute(delete(NewsGalleryImage).where(NewsGalleryImage.id == img_id))
    await db.commit()
    return img


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
        select(NewsAttachment).where(
            NewsAttachment.id == att_id, NewsAttachment.news_id == news_id
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    (_NEWS_MEDIA_DIR / str(news_id) / "attachments" / att.filename).unlink(missing_ok=True)
    await db.execute(delete(NewsAttachment).where(NewsAttachment.id == att_id))
    await db.commit()
    return att
