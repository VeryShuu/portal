"""News API: CRUD новостей."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path
from urllib.parse import quote

import textwrap

from fastapi import APIRouter, Body, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from markdownify import markdownify as _html_to_md
from sqlalchemy import delete, select, update

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.sanitize import escape_text, sanitize_html
from app.core.uploads import stream_upload_to_path
from app.models.news import News as NewsModel
from app.models.news import NewsAttachment, NewsGalleryImage
from app.schemas.news import (
    AttachmentPublic,
    CreateNewsRequest,
    GalleryImagePublic,
    NewsList,
    NewsPublic,
    NewsVersionPublic,
    ReorderItem,
    UpdateNewsRequest,
)
from app.services import news as news_svc
from app.services.audit import push_audit_event

router = APIRouter(prefix="/news", tags=["news"])
logger = get_logger(__name__)

VIEW_DEDUP_TTL = 3600  # 1 час

NEWS_MEDIA_DIR = Path("/data/news_media")
ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_COVER_SIZE = 10 * 1024 * 1024  # 10 MB
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


@router.get("", response_model=NewsList, summary="Список новостей")
async def list_news(
    user: CurrentUser,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> NewsList:
    if status_filter and status_filter not in ("draft", "published", "archived"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")

    if status_filter in ("draft", "archived") and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    items, total = await news_svc.get_news_list(
        db, user=user, status_filter=status_filter, page=page, page_size=page_size
    )
    return NewsList(items=items, total=total)


@router.get("/{news_id}", response_model=NewsPublic, summary="Получить новость")
async def get_news(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    dedup_key = f"view:news:{news_id}:{user.id}"
    if not await redis.exists(dedup_key):
        await redis.setex(dedup_key, VIEW_DEDUP_TTL, "1")
        await news_svc.increment_view_count(db, news_id)

    return news


@router.post("", response_model=NewsPublic, status_code=status.HTTP_201_CREATED, summary="Создать новость")
async def create_news(
    body: CreateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.create_news(db, author=editor, data=body.model_dump())
    await push_audit_event(
        redis,
        event_type="news.created",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news.id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )
    return news


@router.put("/{news_id}", response_model=NewsPublic, summary="Обновить новость")
async def update_news(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    await push_audit_event(
        redis,
        event_type="news.updated",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=updated.title,
        ip_address=request.client.host if request.client else None,
    )
    return updated


@router.put("/{news_id}/draft", response_model=NewsPublic, summary="Автосохранение черновика")
async def save_draft(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only drafts can be auto-saved this way")

    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    return updated


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить новость (soft)")
async def delete_news(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    await news_svc.delete_news(db, news)
    await push_audit_event(
        redis,
        event_type="news.deleted",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )


@router.post("/{news_id}/cover", response_model=NewsPublic, summary="Загрузить обложку новости")
async def upload_news_cover(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported image type. Use JPEG, PNG, WebP or GIF",
        )

    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    news_dir = NEWS_MEDIA_DIR / str(news_id)
    filename = f"cover.{ext}"
    file_path = news_dir / filename

    # P0-4/P0-5: streaming write + real MIME validation via libmagic.
    written, _detected = await stream_upload_to_path(
        file,
        file_path,
        max_size=MAX_COVER_SIZE,
        allowed_mimes=ALLOWED_IMG_TYPES,
    )
    logger.info("news.cover_stored", news_id=str(news_id), size=written)

    relative_path = f"{news_id}/{filename}"
    await db.execute(
        update(NewsModel).where(NewsModel.id == news_id).values(cover_image=relative_path)
    )
    await db.commit()
    await db.refresh(news)

    await push_audit_event(
        redis,
        event_type="news.cover_uploaded",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )
    return news


@router.delete("/{news_id}/cover", response_model=NewsPublic, summary="Удалить обложку новости")
async def delete_news_cover(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    if news.cover_image:
        cover_path = NEWS_MEDIA_DIR / news.cover_image
        if cover_path.exists():
            cover_path.unlink(missing_ok=True)
        news_dir = NEWS_MEDIA_DIR / str(news_id)
        if news_dir.exists() and not any(news_dir.iterdir()):
            news_dir.rmdir()

    await db.execute(
        update(NewsModel).where(NewsModel.id == news_id).values(cover_image=None)
    )
    await db.commit()
    await db.refresh(news)

    # P1-22: audit deletion of cover image.
    await push_audit_event(
        redis,
        event_type="news.cover_deleted",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )
    return news


@router.get("/{news_id}/versions", response_model=list[NewsVersionPublic], summary="История версий")
async def get_versions(
    news_id: uuid.UUID,
    _: EditorDep,
    db: DbDep,
) -> list[NewsVersionPublic]:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return await news_svc.get_news_versions(db, news_id)


# ── Gallery ──────────────────────────────────────────────────────────────────

@router.get("/{news_id}/gallery", response_model=list[GalleryImagePublic], summary="Галерея новости")
async def get_gallery(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> list[GalleryImagePublic]:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news_id)
        .order_by(NewsGalleryImage.sort_order, NewsGalleryImage.created_at)
    )
    return result.scalars().all()


@router.post(
    "/{news_id}/gallery",
    response_model=GalleryImagePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фото в галерею",
)
async def upload_gallery_image(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
) -> GalleryImagePublic:
    settings = get_settings()
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported image type. Use JPEG, PNG, WebP or GIF",
        )

    result = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news_id)
        .order_by(NewsGalleryImage.sort_order.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    next_order = (last.sort_order + 1) if last else 0

    img_id = uuid.uuid4()
    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    filename = f"{img_id}.{ext}"

    gallery_dir = NEWS_MEDIA_DIR / str(news_id) / "gallery"
    dest = gallery_dir / filename

    # P0-4/P0-5: streaming write + real MIME check.
    written, _detected = await stream_upload_to_path(
        file,
        dest,
        max_size=settings.news_attachment_max_size_bytes,
        allowed_mimes=ALLOWED_IMG_TYPES,
    )

    img = NewsGalleryImage(
        id=img_id,
        news_id=news_id,
        filename=filename,
        original_name=file.filename or filename,
        sort_order=next_order,
        file_size=written,
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)
    return img


@router.patch("/{news_id}/gallery/reorder", response_model=list[GalleryImagePublic], summary="Изменить порядок галереи")
async def reorder_gallery(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    items: list[ReorderItem] = Body(...),
) -> list[GalleryImagePublic]:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    for item in items:
        await db.execute(
            update(NewsGalleryImage)
            .where(NewsGalleryImage.id == item.id, NewsGalleryImage.news_id == news_id)
            .values(sort_order=item.sort_order)
        )
    await db.commit()

    result = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news_id)
        .order_by(NewsGalleryImage.sort_order, NewsGalleryImage.created_at)
    )
    return result.scalars().all()


@router.delete("/{news_id}/gallery/{img_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить фото из галереи")
async def delete_gallery_image(
    news_id: uuid.UUID,
    img_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    result = await db.execute(
        select(NewsGalleryImage).where(
            NewsGalleryImage.id == img_id, NewsGalleryImage.news_id == news_id
        )
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    file_path = NEWS_MEDIA_DIR / str(news_id) / "gallery" / img.filename
    file_path.unlink(missing_ok=True)

    await db.execute(delete(NewsGalleryImage).where(NewsGalleryImage.id == img_id))
    await db.commit()

    # P1-22: audit deletion of gallery image.
    await push_audit_event(
        redis,
        event_type="news.gallery_image_deleted",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news_gallery_image",
        resource_id=str(img_id),
        resource_title=img.original_name,
        ip_address=request.client.host if request.client else None,
        metadata={"news_id": str(news_id)},
    )


# ── Attachments ───────────────────────────────────────────────────────────────

@router.get("/{news_id}/attachments", response_model=list[AttachmentPublic], summary="Вложения новости")
async def get_attachments(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> list[AttachmentPublic]:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(NewsAttachment)
        .where(NewsAttachment.news_id == news_id)
        .order_by(NewsAttachment.created_at)
    )
    return result.scalars().all()


@router.post(
    "/{news_id}/attachments",
    response_model=AttachmentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить вложение",
)
async def upload_attachment(
    news_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
) -> AttachmentPublic:
    settings = get_settings()
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    att_id = uuid.uuid4()
    dest = NEWS_MEDIA_DIR / str(news_id) / "attachments" / str(att_id)

    # P0-4/P0-5: streaming write + libmagic-detected MIME (used for serving later).
    written, detected_mime = await stream_upload_to_path(
        file,
        dest,
        max_size=settings.news_attachment_max_size_bytes,
        allowed_mimes=None,  # attachments accept any type
    )

    att = NewsAttachment(
        id=att_id,
        news_id=news_id,
        filename=str(att_id),
        original_name=file.filename or str(att_id),
        mime_type=detected_mime or file.content_type,
        file_size=written,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


@router.get("/{news_id}/attachments/{att_id}/download", summary="Скачать вложение")
async def download_attachment(
    news_id: uuid.UUID,
    att_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> FileResponse:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(NewsAttachment).where(
            NewsAttachment.id == att_id, NewsAttachment.news_id == news_id
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    file_path = NEWS_MEDIA_DIR / str(news_id) / "attachments" / att.filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=att.original_name,
        media_type=att.mime_type or "application/octet-stream",
    )


@router.delete("/{news_id}/attachments/{att_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить вложение")
async def delete_attachment(
    news_id: uuid.UUID,
    att_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    result = await db.execute(
        select(NewsAttachment).where(
            NewsAttachment.id == att_id, NewsAttachment.news_id == news_id
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    file_path = NEWS_MEDIA_DIR / str(news_id) / "attachments" / att.filename
    file_path.unlink(missing_ok=True)

    await db.execute(delete(NewsAttachment).where(NewsAttachment.id == att_id))
    await db.commit()

    # P1-22: audit deletion of news attachment.
    await push_audit_event(
        redis,
        event_type="news.attachment_deleted",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news_attachment",
        resource_id=str(att_id),
        resource_title=att.original_name,
        ip_address=request.client.host if request.client else None,
        metadata={"news_id": str(news_id)},
    )


# ── Export ────────────────────────────────────────────────────────────────────

_EXPORT_CSS = textwrap.dedent("""
    *, *::before, *::after { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 16px; line-height: 1.75; color: #1a1a2e;
        max-width: 820px; margin: 40px auto; padding: 0 24px;
    }
    h1 { font-size: 2em; font-weight: 800; margin: 0 0 8px; line-height: 1.2; }
    h2 { font-size: 1.4em; font-weight: 700; margin-top: 2em; }
    h3 { font-size: 1.15em; font-weight: 700; margin-top: 1.6em; }
    .meta { font-size: 13px; color: #666; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 2px solid #eee; }
    .cover { margin-bottom: 28px; }
    .cover img { width: 100%; max-height: 420px; object-fit: cover; border-radius: 10px; }
    img { max-width: 100%; border-radius: 8px; }
    pre { background: #f4f4f8; padding: 14px 16px; border-radius: 8px; overflow-x: auto; font-size: 14px; }
    code { background: #f4f4f8; padding: 2px 5px; border-radius: 4px; font-size: 0.9em; }
    pre code { background: none; padding: 0; }
    blockquote { border-left: 3px solid #c0392b; padding-left: 16px; margin-left: 0; color: #555; font-style: italic; }
    a { color: #2980b9; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; }
    th { background: #f4f4f8; font-weight: 700; }
    .gallery-section { margin-top: 40px; }
    .gallery-section h2 { font-size: 1.2em; color: #555; margin-bottom: 12px; }
    .gallery-grid { display: flex; flex-wrap: wrap; gap: 10px; }
    .gallery-grid img { width: calc(33% - 10px); min-width: 120px; height: 160px; object-fit: cover; border-radius: 8px; }
""").strip()


def _file_to_data_uri(path: Path) -> str | None:
    try:
        if not path or not path.exists():
            return None
        ext = path.suffix.lower().lstrip(".")
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp", "gif": "image/gif",
        }.get(ext, "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    except Exception:
        return None


def _inline_body_images(body: str) -> str:
    media_root = NEWS_MEDIA_DIR.resolve()

    def _replace(m: re.Match) -> str:
        url = m.group(1)
        if url.startswith("/media/news/"):
            rel = url.removeprefix("/media/news/")
            # P0-7: prevent path traversal — ensure resolved path stays inside NEWS_MEDIA_DIR.
            try:
                target = (NEWS_MEDIA_DIR / rel).resolve()
                target.relative_to(media_root)
            except (ValueError, OSError):
                return m.group(0)
            uri = _file_to_data_uri(target)
            if uri:
                return f'src="{uri}"'
        return m.group(0)
    return re.sub(r'src="(/media/news/[^"]+)"', _replace, body)


def _build_export_html(
    news: NewsModel,
    for_pdf: bool = False,
    cover_uri: str | None = None,
    gallery_uris: list[tuple[str, str]] | None = None,
) -> str:
    date_str = ""
    if news.published_at:
        date_str = news.published_at.strftime("%d.%m.%Y")
    elif news.created_at:
        date_str = news.created_at.strftime("%d.%m.%Y")

    extra_css = "@page { margin: 20mm 15mm; }" if for_pdf else ""

    # P0-1: escape title and date — they are interpolated into HTML attributes / text.
    safe_title = escape_text(news.title)
    safe_date = escape_text(date_str)

    cover_html = ""
    if cover_uri:
        cover_html = f'<div class="cover"><img src="{cover_uri}" alt="Обложка новости"></div>'

    # P0-1/P0-2: body is sanitized on write, but re-clean on export as defence-in-depth
    # (older rows from before the sanitizer was added may still contain raw HTML).
    body_html = _inline_body_images(sanitize_html(news.body))

    gallery_html = ""
    if gallery_uris:
        imgs = "".join(
            f'<img src="{uri}" alt="{escape_text(alt)}">' for uri, alt in gallery_uris
        )
        gallery_html = f'<div class="gallery-section"><h2>Галерея</h2><div class="gallery-grid">{imgs}</div></div>'

    return textwrap.dedent(f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{safe_title}</title>
        <style>
        {_EXPORT_CSS}
        {extra_css}
        </style>
        </head>
        <body>
        {cover_html}
        <h1>{safe_title}</h1>
        <div class="meta">{safe_date}</div>
        <div class="body">{body_html}</div>
        {gallery_html}
        </body>
        </html>
    """).strip()


async def _load_export_media(
    news: NewsModel,
    db: DbDep,
) -> tuple[str | None, list[tuple[str, str]]]:
    import asyncio as _asyncio

    cover_uri: str | None = None
    if news.cover_image:
        # P1-19: read file off the event loop — base64 encoding of large covers
        # otherwise blocks all coroutines for hundreds of ms.
        cover_uri = await _asyncio.to_thread(_file_to_data_uri, NEWS_MEDIA_DIR / news.cover_image)

    result = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news.id)
        .order_by(NewsGalleryImage.sort_order, NewsGalleryImage.created_at)
    )
    gallery_images = result.scalars().all()
    gallery_uris: list[tuple[str, str]] = []
    for img in gallery_images:
        path = NEWS_MEDIA_DIR / str(news.id) / "gallery" / img.filename
        uri = await _asyncio.to_thread(_file_to_data_uri, path)
        if uri:
            gallery_uris.append((uri, img.original_name))

    return cover_uri, gallery_uris


async def _render_pdf(html: str) -> bytes:
    # P1-18: reuse the singleton Chromium launched in lifespan.
    from app.core.pdf import render_pdf
    return await render_pdf(html)


def _content_disposition(title: str, ext: str) -> str:
    fname = f"{title}.{ext}"
    ascii_fallback = "".join(c if ord(c) < 128 and (c.isalnum() or c in " -_.") else "_" for c in title).strip()[:60] or "news"
    ascii_fname = f"{ascii_fallback}.{ext}"
    encoded = quote(fname, safe="")
    return f'attachment; filename="{ascii_fname}"; filename*=UTF-8\'\'{encoded}'


@router.get("/{news_id}/export/html", summary="Экспорт новости в HTML")
async def export_html(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cover_uri, gallery_uris = await _load_export_media(news, db)
    html = _build_export_html(news, cover_uri=cover_uri, gallery_uris=gallery_uris)
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(news.title, "html")},
    )


@router.get("/{news_id}/export/markdown", summary="Экспорт новости в Markdown")
async def export_markdown(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    date_str = ""
    if news.published_at:
        date_str = news.published_at.strftime("%d.%m.%Y")
    elif news.created_at:
        date_str = news.created_at.strftime("%d.%m.%Y")

    cover_uri, gallery_uris = await _load_export_media(news, db)

    lines: list[str] = [f"# {news.title}", "", f"_{date_str}_", "", "---", ""]
    if cover_uri:
        lines += [f"![Обложка]({cover_uri})", ""]
    body_md = _html_to_md(news.body, heading_style="ATX", bullets="-", strip=["script", "style"])
    lines += [body_md.strip(), ""]
    if gallery_uris:
        lines += ["## Галерея", ""]
        for uri, alt in gallery_uris:
            lines.append(f"![{alt}]({uri})")
        lines.append("")

    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(news.title, "md")},
    )


@router.get("/{news_id}/export/pdf", summary="Экспорт новости в PDF")
async def export_pdf(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cover_uri, gallery_uris = await _load_export_media(news, db)
    html = _build_export_html(news, for_pdf=True, cover_uri=cover_uri, gallery_uris=gallery_uris)
    try:
        pdf_bytes = await _render_pdf(html)
    except Exception as exc:
        logger.error("PDF render failed", news_id=str(news_id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PDF generation failed")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(news.title, "pdf")},
    )
