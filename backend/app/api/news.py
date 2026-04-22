"""News API: CRUD новостей."""
from __future__ import annotations

import uuid
from pathlib import Path

import textwrap

from fastapi import APIRouter, Body, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from markdownify import markdownify as _html_to_md
from sqlalchemy import delete, select, update

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
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

    content = await file.read()
    if len(content) > MAX_COVER_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Cover image too large (max 10 MB)",
        )

    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    news_dir = NEWS_MEDIA_DIR / str(news_id)
    news_dir.mkdir(parents=True, exist_ok=True)
    filename = f"cover.{ext}"
    file_path = news_dir / filename

    with open(file_path, "wb") as f:
        f.write(content)

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

    content = await file.read()
    if len(content) > settings.news_attachment_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {settings.news_attachment_max_size_mb} MB)",
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
    gallery_dir.mkdir(parents=True, exist_ok=True)
    (gallery_dir / filename).write_bytes(content)

    img = NewsGalleryImage(
        id=img_id,
        news_id=news_id,
        filename=filename,
        original_name=file.filename or filename,
        sort_order=next_order,
        file_size=len(content),
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)
    return img


@router.patch("/{news_id}/gallery/reorder", response_model=list[GalleryImagePublic], summary="Изменить порядок галереи")
async def reorder_gallery(
    news_id: uuid.UUID,
    items: list[ReorderItem] = Body(...),
    editor: EditorDep = ...,
    db: DbDep = ...,
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

    content = await file.read()
    if len(content) > settings.news_attachment_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {settings.news_attachment_max_size_mb} MB)",
        )

    att_id = uuid.uuid4()
    attachments_dir = NEWS_MEDIA_DIR / str(news_id) / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    (attachments_dir / str(att_id)).write_bytes(content)

    att = NewsAttachment(
        id=att_id,
        news_id=news_id,
        filename=str(att_id),
        original_name=file.filename or str(att_id),
        mime_type=file.content_type,
        file_size=len(content),
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


# ── Export ────────────────────────────────────────────────────────────────────

_EXPORT_CSS = textwrap.dedent("""
    *, *::before, *::after { box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 16px; line-height: 1.75; color: #1a1a2e;
        max-width: 800px; margin: 40px auto; padding: 0 24px;
    }
    h1 { font-size: 2em; font-weight: 800; margin: 0 0 8px; line-height: 1.2; }
    h2 { font-size: 1.4em; font-weight: 700; margin-top: 2em; }
    h3 { font-size: 1.15em; font-weight: 700; margin-top: 1.6em; }
    .meta { font-size: 13px; color: #666; margin-bottom: 32px; padding-bottom: 16px; border-bottom: 2px solid #eee; }
    img { max-width: 100%; border-radius: 8px; }
    pre { background: #f4f4f8; padding: 14px 16px; border-radius: 8px; overflow-x: auto; font-size: 14px; }
    code { background: #f4f4f8; padding: 2px 5px; border-radius: 4px; font-size: 0.9em; }
    pre code { background: none; padding: 0; }
    blockquote { border-left: 3px solid #c0392b; padding-left: 16px; margin-left: 0; color: #555; font-style: italic; }
    a { color: #2980b9; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; }
    th { background: #f4f4f8; font-weight: 700; }
""").strip()


def _build_export_html(news: NewsModel, for_pdf: bool = False) -> str:
    date_str = ""
    if news.published_at:
        date_str = news.published_at.strftime("%d.%m.%Y")
    elif news.created_at:
        date_str = news.created_at.strftime("%d.%m.%Y")

    extra_css = "@page { margin: 20mm 15mm; }" if for_pdf else ""

    return textwrap.dedent(f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{news.title}</title>
        <style>
        {_EXPORT_CSS}
        {extra_css}
        </style>
        </head>
        <body>
        <h1>{news.title}</h1>
        <div class="meta">{date_str}</div>
        <div class="body">{news.body}</div>
        </body>
        </html>
    """).strip()


async def _render_pdf(html: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
        )
        await browser.close()
    return pdf_bytes


def _safe_filename(title: str, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()[:60]
    return f"{safe or 'news'}.{ext}"


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

    html = _build_export_html(news)
    fname = _safe_filename(news.title, "html")
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
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

    body_md = _html_to_md(news.body, heading_style="ATX", bullets="-", strip=["script", "style"])
    md_content = f"# {news.title}\n\n_{date_str}_\n\n---\n\n{body_md.strip()}\n"

    fname = _safe_filename(news.title, "md")
    return Response(
        content=md_content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
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

    html = _build_export_html(news, for_pdf=True)
    try:
        pdf_bytes = await _render_pdf(html)
    except Exception as exc:
        logger.error("PDF render failed", news_id=str(news_id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="PDF generation failed")

    fname = _safe_filename(news.title, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
