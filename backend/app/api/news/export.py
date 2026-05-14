"""News export routes (HTML / Markdown / PDF) and rendering helpers."""

from __future__ import annotations

import asyncio
import base64
import re
import textwrap
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from markdownify import markdownify as _html_to_md
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.core.sanitize import escape_text, sanitize_html
from app.models.news import News as NewsModel
from app.models.news import NewsGalleryImage
from app.services import news as news_svc

from ._common import NEWS_MEDIA_DIR, logger, require_news_read_access

router = APIRouter()


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

MAX_EXPORT_IMG_BYTES = 10 * 1024 * 1024

_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _file_to_data_uri(path: Path) -> str | None:
    try:
        if not path or not path.exists():
            return None
        ext = path.suffix.lower().lstrip(".")
        mime = _MIME_BY_EXT.get(ext, "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    except Exception:
        return None


def _file_to_data_uri_resized(path: Path, max_dim: int = 1200, quality: int = 72) -> str | None:
    try:
        if not path or not path.exists():
            return None
        from io import BytesIO

        from PIL import Image

        with Image.open(path) as src:
            rgb = src.convert("RGB")
            rgb.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = BytesIO()
            rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return _file_to_data_uri(path)


def _inline_body_images(body: str) -> str:
    media_root = NEWS_MEDIA_DIR.resolve()

    def _replace(m: re.Match) -> str:
        url = m.group(1)
        if url.startswith("/media/news/"):
            rel = url.removeprefix("/media/news/")
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
    *,
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

    safe_title = escape_text(news.title)
    safe_date = escape_text(date_str)

    cover_html = ""
    if cover_uri:
        cover_html = f'<div class="cover"><img src="{cover_uri}" alt="Обложка новости"></div>'

    body_html = _inline_body_images(sanitize_html(news.body))

    gallery_html = ""
    if gallery_uris:
        imgs = "".join(f'<img src="{uri}" alt="{escape_text(alt)}">' for uri, alt in gallery_uris)
        gallery_html = (
            f'<div class="gallery-section"><h2>Галерея</h2>'
            f'<div class="gallery-grid">{imgs}</div></div>'
        )

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


def _is_within_size_limit(path: Path, news_id: uuid.UUID, kind: str) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size > MAX_EXPORT_IMG_BYTES:
        logger.warning(
            "news.export.image_skipped_too_large",
            news_id=str(news_id),
            kind=kind,
            path=str(path),
            size=size,
            max_size=MAX_EXPORT_IMG_BYTES,
        )
        return False
    return True


async def _load_export_media(
    news: NewsModel,
    db: DbDep,
    *,
    for_pdf: bool = False,
) -> tuple[str | None, list[tuple[str, str]]]:
    to_uri = _file_to_data_uri_resized if for_pdf else _file_to_data_uri

    cover_uri: str | None = None
    if news.cover_image:
        cover_path = NEWS_MEDIA_DIR / news.cover_image
        if _is_within_size_limit(cover_path, news.id, "cover"):
            cover_uri = await asyncio.to_thread(to_uri, cover_path)

    result = await db.execute(
        select(NewsGalleryImage)
        .where(NewsGalleryImage.news_id == news.id)
        .order_by(NewsGalleryImage.sort_order, NewsGalleryImage.created_at)
    )
    gallery_uris: list[tuple[str, str]] = []
    for img in result.scalars().all():
        path = NEWS_MEDIA_DIR / str(news.id) / "gallery" / img.filename
        if not _is_within_size_limit(path, news.id, "gallery"):
            continue
        uri = await asyncio.to_thread(to_uri, path)
        if uri:
            gallery_uris.append((uri, img.original_name))

    return cover_uri, gallery_uris


def _content_disposition(title: str, ext: str) -> str:
    fname = f"{title}.{ext}"
    ascii_fallback = (
        "".join(c if ord(c) < 128 and (c.isalnum() or c in " -_.") else "_" for c in title).strip()[
            :60
        ]
        or "news"
    )
    ascii_fname = f"{ascii_fallback}.{ext}"
    encoded = quote(fname, safe="")
    return f"attachment; filename=\"{ascii_fname}\"; filename*=UTF-8''{encoded}"


async def _load_news_for_export(news_id: uuid.UUID, user, db: DbDep) -> NewsModel:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    require_news_read_access(news, user)
    return news


@router.get("/{news_id}/export/html", summary="Экспорт новости в HTML")
async def export_html(news_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    news = await _load_news_for_export(news_id, user, db)
    cover_uri, gallery_uris = await _load_export_media(news, db)
    html = _build_export_html(news, cover_uri=cover_uri, gallery_uris=gallery_uris)
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(news.title, "html")},
    )


@router.get("/{news_id}/export/markdown", summary="Экспорт новости в Markdown")
async def export_markdown(news_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    news = await _load_news_for_export(news_id, user, db)

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
async def export_pdf(news_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Response:
    news = await _load_news_for_export(news_id, user, db)
    cover_uri, gallery_uris = await _load_export_media(news, db, for_pdf=True)
    html = _build_export_html(news, for_pdf=True, cover_uri=cover_uri, gallery_uris=gallery_uris)
    try:
        from app.core.pdf import render_pdf

        pdf_bytes = await render_pdf(html)
    except Exception as exc:
        logger.exception(
            "news.pdf_render_failed",
            news_id=str(news_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF generation failed",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(news.title, "pdf")},
    )
