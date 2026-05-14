"""News service — бизнес-логика."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

# Responsive cover variants: width in px. Files saved as cover-{w}.webp/avif.
NEWS_COVER_VARIANT_WIDTHS: tuple[int, ...] = (400, 800, 1200, 1600)
_NEWS_COVER_QUALITY = 82

logger = get_logger(__name__)


def _build_cover_variants(
    src: Path, out_dir: Path
) -> tuple[list[int], str | None]:
    """Generate WebP+AVIF variants and return (widths_generated, dominant_hex).

    Best-effort: failures are logged and an empty list is returned, the
    original cover file remains usable as a fallback.
    """
    import contextlib

    try:
        from PIL import Image, ImageOps  # lazy
    except Exception as e:
        logger.warning("news.cover.pillow_missing", error=str(e))
        return [], None

    widths_done: list[int] = []
    dominant_hex: str | None = None
    try:
        with Image.open(src) as src_img:
            pil = ImageOps.exif_transpose(src_img)
            if pil.mode == "P":
                # Palette image: preserve transparency if present, else flatten to RGB.
                pil = pil.convert("RGBA" if "transparency" in pil.info else "RGB")
            elif pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGB")
            try:
                tiny = pil.copy()
                tiny.thumbnail((1, 1), Image.Resampling.LANCZOS)
                px = tiny.convert("RGB").getpixel((0, 0))
                if isinstance(px, tuple) and len(px) >= 3:
                    dominant_hex = f"#{int(px[0]):02x}{int(px[1]):02x}{int(px[2]):02x}"
            except Exception as e:
                logger.warning("news.cover.dominant_failed", error=str(e))

            orig_w = pil.width
            for target_w in NEWS_COVER_VARIANT_WIDTHS:
                if target_w > orig_w:
                    continue
                copy = pil.copy()
                copy.thumbnail((target_w, target_w * 4), Image.Resampling.LANCZOS)
                webp_path = out_dir / f"cover-{target_w}.webp"
                try:
                    copy.save(webp_path, "WEBP", quality=_NEWS_COVER_QUALITY, method=6)
                    widths_done.append(target_w)
                except Exception as e:
                    logger.warning(
                        "news.cover.webp_failed", width=target_w, error=str(e)
                    )
                    continue
                with contextlib.suppress(Exception):
                    copy.save(
                        out_dir / f"cover-{target_w}.avif",
                        "AVIF",
                        quality=_NEWS_COVER_QUALITY,
                    )
            if not widths_done:
                copy = pil.copy()
                webp_path = out_dir / f"cover-{orig_w}.webp"
                try:
                    copy.save(webp_path, "WEBP", quality=_NEWS_COVER_QUALITY, method=6)
                    widths_done.append(orig_w)
                except Exception as e:
                    logger.warning(
                        "news.cover.webp_failed", width=orig_w, error=str(e)
                    )
    except Exception as e:
        logger.warning("news.cover.variants_failed", error=str(e))
    return widths_done, dominant_hex


def _remove_cover_variants(news_id_dir: Path) -> None:
    if not news_id_dir.exists():
        return
    for p in news_id_dir.glob("cover-*.webp"):
        p.unlink(missing_ok=True)
    for p in news_id_dir.glob("cover-*.avif"):
        p.unlink(missing_ok=True)


def _targeting_filter(stmt, user: User):
    """Фильтр по таргетингу: показывать новость, если ОБА условия:
    - target_departments пуст ИЛИ содержит отдел пользователя
    - target_roles пуст ИЛИ содержит роль пользователя
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
    offset_override: int | None = None,
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

    effective_offset = offset_override if offset_override is not None else (page - 1) * page_size
    stmt = stmt.offset(effective_offset).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_news_by_id(
    db: AsyncSession, news_id: uuid.UUID, *, include_deleted: bool = False
) -> News | None:
    stmt = select(News).where(News.id == news_id)
    if not include_deleted:
        stmt = stmt.where(News.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_news(db: AsyncSession, *, author: User, data: dict) -> News:
    now = datetime.now(UTC)
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
    news.previous_status = news.status
    news.deleted_at = datetime.now(UTC)
    news.status = "archived"
    await db.commit()


async def get_trash_news(
    db: AsyncSession, *, page: int = 1, page_size: int = 20
) -> tuple[list[News], int]:
    base = select(News).where(News.deleted_at.is_not(None))
    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_stmt)).scalar_one()
    stmt = (
        base.options(selectinload(News.author))
        .order_by(News.deleted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def restore_news(db: AsyncSession, news: News) -> News:
    news.deleted_at = None
    if news.previous_status:
        news.status = news.previous_status
        news.previous_status = None
    await db.commit()
    await db.refresh(news)
    return news


async def purge_news(db: AsyncSession, news: News) -> None:
    news_id = news.id
    shutil.rmtree(_NEWS_MEDIA_DIR / str(news_id), ignore_errors=True)
    await db.execute(
        text("DELETE FROM bookmarks WHERE resource_type='news' AND resource_id = :rid"),
        {"rid": str(news_id)},
    )
    # Используем DELETE-statement (не db.delete(news)), чтобы Postgres сам
    # выполнил ON DELETE CASCADE для news_versions / news_gallery_images /
    # news_attachments. ORM-side relationship News.versions не имеет
    # passive_deletes=True и иначе пытался бы UPDATE news_id=NULL.
    await db.execute(delete(News).where(News.id == news_id))
    await db.commit()
    logger.info("news.purged", news_id=str(news_id))


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
