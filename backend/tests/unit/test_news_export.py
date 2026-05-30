"""Unit-тесты api/news/export.py (Phase 4.8).

Покрытие:
- _file_to_data_uri: файл не существует / None path / happy-path / неизвестный ext
- _file_to_data_uri_resized: файл не существует / ошибка PIL → fallback / happy-path
- _inline_body_images: нет совпадений / /media/news/ URL → data URI / path traversal blocked
- _build_export_html: без cover/gallery / с cover / с gallery / for_pdf режим
- _is_within_size_limit: файл не существует / слишком большой / ok
- _content_disposition: ASCII title / Unicode title / пустое название
- GET /news/{id}/export/html: 200 ok / 404 не найден / 403 доступ запрещён
- GET /news/{id}/export/markdown: 200 ok / нет обложки
- GET /news/{id}/export/pdf: 200 ok / 503 при ошибке рендера
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

_NEWS_SVC = "app.api.news.export.news_svc"


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
    )


def _make_news(
    *,
    status: str = "published",
    title: str = "Test News",
    body: str = "<p>Body</p>",
    cover_image: str | None = None,
    published_at=None,
    deleted_at=None,
) -> MagicMock:
    news = MagicMock()
    news.id = uuid.uuid4()
    news.title = title
    news.body = body
    news.status = status
    news.cover_image = cover_image
    news.published_at = published_at
    news.created_at = datetime.now(UTC)
    news.deleted_at = deleted_at
    return news


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _build_app(user: SimpleNamespace, db: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db
    from app.api.news.export import router

    _app = FastAPI()
    _app.include_router(router, prefix="/news")

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


# ── _file_to_data_uri ─────────────────────────────────────────────────────────


class TestFileToDataUri:
    def test_returns_none_for_nonexistent_path(self, tmp_path):
        from app.api.news.export import _file_to_data_uri

        result = _file_to_data_uri(tmp_path / "nonexistent.png")
        assert result is None

    def test_returns_none_for_none_path(self):
        from app.api.news.export import _file_to_data_uri

        result = _file_to_data_uri(None)
        assert result is None

    def test_returns_data_uri_for_existing_file(self, tmp_path):
        from app.api.news.export import _file_to_data_uri

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")
        result = _file_to_data_uri(img)
        assert result is not None
        assert result.startswith("data:image/png;base64,")

    def test_uses_jpeg_mime_for_jpg_extension(self, tmp_path):
        from app.api.news.export import _file_to_data_uri

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        result = _file_to_data_uri(img)
        assert result is not None
        assert "image/jpeg" in result

    def test_uses_default_mime_for_unknown_extension(self, tmp_path):
        from app.api.news.export import _file_to_data_uri

        img = tmp_path / "photo.xyz"
        img.write_bytes(b"data")
        result = _file_to_data_uri(img)
        assert result is not None
        assert "image/jpeg" in result


# ── _file_to_data_uri_resized ─────────────────────────────────────────────────


class TestFileToDataUriResized:
    def test_returns_none_for_nonexistent_path(self, tmp_path):
        from app.api.news.export import _file_to_data_uri_resized

        result = _file_to_data_uri_resized(tmp_path / "nonexistent.png")
        assert result is None

    def test_falls_back_to_original_on_pil_error(self, tmp_path):
        from app.api.news.export import _file_to_data_uri_resized

        img = tmp_path / "test.png"
        img.write_bytes(b"not a real image")

        with patch("app.api.news.export._file_to_data_uri", return_value="data:fallback"):
            result = _file_to_data_uri_resized(img)

        assert result == "data:fallback"


# ── _inline_body_images ───────────────────────────────────────────────────────


class TestInlineBodyImages:
    def test_leaves_non_media_srcs_unchanged(self):
        from app.api.news.export import _inline_body_images

        html = '<img src="https://example.com/img.png">'
        result = _inline_body_images(html)
        assert result == html

    def test_replaces_media_news_src_with_data_uri(self, tmp_path):
        from app.api.news.export import _inline_body_images

        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG\r\n")

        with patch("app.api.news.export.NEWS_MEDIA_DIR", tmp_path):
            html = '<img src="/media/news/photo.png">'
            result = _inline_body_images(html)

        assert "data:image/png;base64," in result

    def test_skips_media_if_uri_returns_none(self, tmp_path):
        from app.api.news.export import _inline_body_images

        with patch("app.api.news.export.NEWS_MEDIA_DIR", tmp_path):
            html = '<img src="/media/news/missing.png">'
            result = _inline_body_images(html)

        assert result == html

    def test_blocks_path_traversal(self, tmp_path):
        from app.api.news.export import _inline_body_images

        with patch("app.api.news.export.NEWS_MEDIA_DIR", tmp_path):
            html = '<img src="/media/news/../../../etc/passwd">'
            result = _inline_body_images(html)

        assert "data:" not in result


# ── _build_export_html ────────────────────────────────────────────────────────


class TestBuildExportHtml:
    def test_builds_html_without_cover_or_gallery(self):
        from app.api.news.export import _build_export_html

        news = _make_news(title="My News", body="<p>Hello</p>")
        html = _build_export_html(news)
        assert "My News" in html
        assert "<!DOCTYPE html>" in html
        assert '<div class="gallery-section">' not in html

    def test_includes_cover_when_provided(self):
        from app.api.news.export import _build_export_html

        news = _make_news()
        html = _build_export_html(news, cover_uri="data:image/png;base64,abc")
        assert "cover" in html
        assert "data:image/png;base64,abc" in html

    def test_includes_gallery_when_provided(self):
        from app.api.news.export import _build_export_html

        news = _make_news()
        gallery_uris = [("data:image/png;base64,abc", "Photo 1")]
        html = _build_export_html(news, gallery_uris=gallery_uris)
        assert "gallery" in html.lower()
        assert "Photo 1" in html

    def test_adds_page_css_for_pdf(self):
        from app.api.news.export import _build_export_html

        news = _make_news()
        html = _build_export_html(news, for_pdf=True)
        assert "@page" in html

    def test_formats_published_date(self):

        from app.api.news.export import _build_export_html

        pub = datetime(2024, 3, 15, tzinfo=UTC)
        news = _make_news(published_at=pub)
        html = _build_export_html(news)
        assert "15.03.2024" in html

    def test_falls_back_to_created_at_when_no_published_at(self):
        from app.api.news.export import _build_export_html

        news = _make_news()
        news.published_at = None
        html = _build_export_html(news)
        assert "<!DOCTYPE html>" in html

    def test_escapes_title_html(self):
        from app.api.news.export import _build_export_html

        news = _make_news(title="<script>alert(1)</script>")
        html = _build_export_html(news)
        assert "<script>alert(1)</script>" not in html


# ── _is_within_size_limit ─────────────────────────────────────────────────────


class TestIsWithinSizeLimit:
    def test_returns_false_for_nonexistent_file(self, tmp_path):
        from app.api.news.export import _is_within_size_limit

        result = _is_within_size_limit(tmp_path / "missing.png", uuid.uuid4(), "cover")
        assert result is False

    def test_returns_false_for_oversized_file(self, tmp_path):
        from app.api.news.export import MAX_EXPORT_IMG_BYTES, _is_within_size_limit

        f = tmp_path / "big.png"
        f.write_bytes(b"x" * (MAX_EXPORT_IMG_BYTES + 1))
        result = _is_within_size_limit(f, uuid.uuid4(), "cover")
        assert result is False

    def test_returns_true_for_acceptable_file(self, tmp_path):
        from app.api.news.export import _is_within_size_limit

        f = tmp_path / "small.png"
        f.write_bytes(b"x" * 100)
        result = _is_within_size_limit(f, uuid.uuid4(), "cover")
        assert result is True


# ── _content_disposition ──────────────────────────────────────────────────────


class TestContentDisposition:
    def test_ascii_title(self):
        from app.api.news.export import _content_disposition

        cd = _content_disposition("My News", "html")
        assert "My News.html" in cd

    def test_unicode_title_includes_utf8_encoded(self):
        from app.api.news.export import _content_disposition

        cd = _content_disposition("Новость", "md")
        assert "filename*=UTF-8''" in cd
        assert ".md" in cd

    def test_empty_title_falls_back_to_news(self):
        from app.api.news.export import _content_disposition

        cd = _content_disposition("", "pdf")
        assert "news.pdf" in cd


# ── GET /news/{id}/export/html ────────────────────────────────────────────────


class TestExportHtml:
    @pytest.mark.asyncio
    async def test_returns_200_with_html_content(self):
        user = _make_user()
        db = _make_db()
        news = _make_news(status="published")

        db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch("app.api.news.export.asyncio.to_thread", new=AsyncMock(return_value=None)),
        ):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/html")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_returns_404_when_news_not_found(self):
        user = _make_user()
        db = _make_db()

        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{uuid.uuid4()}/export/html")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_403_when_access_denied(self):
        user = _make_user(role="reader")
        db = _make_db()
        news = _make_news(status="draft")

        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/html")

        assert resp.status_code == 403


# ── GET /news/{id}/export/markdown ────────────────────────────────────────────


class TestExportMarkdown:
    @pytest.mark.asyncio
    async def test_returns_200_with_markdown_content(self):
        user = _make_user()
        db = _make_db()
        news = _make_news(status="published", body="<p>Hello world</p>")

        db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch("app.api.news.export.asyncio.to_thread", new=AsyncMock(return_value=None)),
        ):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/markdown")

        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_includes_published_date_when_set(self):
        user = _make_user()
        db = _make_db()
        pub = datetime(2024, 6, 1, tzinfo=UTC)
        news = _make_news(status="published", published_at=pub)

        db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch("app.api.news.export.asyncio.to_thread", new=AsyncMock(return_value=None)),
        ):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/markdown")

        assert resp.status_code == 200
        assert b"01.06.2024" in resp.content


# ── GET /news/{id}/export/pdf ─────────────────────────────────────────────────


class TestExportPdf:
    @pytest.mark.asyncio
    async def test_returns_200_with_pdf_content(self):
        user = _make_user()
        db = _make_db()
        news = _make_news(status="published")

        db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch("app.api.news.export.asyncio.to_thread", new=AsyncMock(return_value=None)),
            patch("app.core.pdf.render_pdf", new=AsyncMock(return_value=b"%PDF-1.4")),
        ):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/pdf")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_returns_503_when_pdf_render_fails(self):
        user = _make_user()
        db = _make_db()
        news = _make_news(status="published")

        db.execute.return_value.scalars.return_value.all.return_value = []

        async def _fail_render(html):
            raise RuntimeError("chromium not found")

        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch("app.api.news.export.asyncio.to_thread", new=AsyncMock(return_value=None)),
            patch("app.core.pdf.render_pdf", new=_fail_render),
        ):
            app = _build_app(user, db)
            resp = await _get(app, f"/news/{news.id}/export/pdf")

        assert resp.status_code == 503
