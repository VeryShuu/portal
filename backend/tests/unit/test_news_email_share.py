"""Unit-тесты рассылки новости по email (services/news/email_share.py + endpoint).

Покрытие:
- build_news_excerpt: strip Markdown, обрезка по лимиту
- build_share_email_content: HTML-escape заголовка/excerpt, наличие ссылки
- share_news_by_email: N строк в outbox, изоляция сбойного получателя (begin_nested)
- POST /news/{id}/share-email: 409 для draft, 200 для published, валидация ids
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

from app.services.news import email_share

_SHARE = "app.services.news.email_share"


# ── build_news_excerpt ──────────────────────────────────────────────────────


class TestBuildNewsExcerpt:
    def test_strips_markdown_tokens(self):
        out = email_share.build_news_excerpt("# Заголовок\n\n**жирный** _курсив_ `code`")
        assert "#" not in out
        assert "*" not in out
        assert "`" not in out
        assert "жирный" in out and "курсив" in out

    def test_link_keeps_text_drops_url(self):
        out = email_share.build_news_excerpt("Смотри [тут](https://example.com/secret)")
        assert "тут" in out
        assert "example.com" not in out

    def test_image_removed(self):
        out = email_share.build_news_excerpt("До ![alt](http://x/y.png) после")
        assert "До" in out and "после" in out
        assert "y.png" not in out

    def test_code_fence_removed(self):
        out = email_share.build_news_excerpt("Текст ```\nrm -rf /\n``` конец")
        assert "rm -rf" not in out

    def test_truncates_with_ellipsis(self):
        out = email_share.build_news_excerpt("a" * 500, limit=100)
        assert out.endswith("…")
        assert len(out) <= 101

    def test_empty_body(self):
        assert email_share.build_news_excerpt(None) == ""


# ── build_share_email_content ───────────────────────────────────────────────


class TestBuildShareEmailContent:
    def test_escapes_title_and_excerpt(self):
        html, _text = email_share.build_share_email_content(
            news_title="<script>x</script>",
            excerpt="a & b <img>",
            news_link="https://portal.local/news/1",
        )
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    def test_contains_link(self):
        link = "https://portal.local/news/42"
        html, text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link=link
        )
        assert link in html
        assert link in text

    def test_newlines_to_br_in_html(self):
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="line1\nline2", news_link="http://x"
        )
        assert "<br>" in html

    def test_brand_name_appears_once(self):
        html, text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x", portal_name="Мой портал"
        )
        assert html.count("Мой портал") == 1
        assert "Мой портал" in text

    def test_eyebrow_defaults_to_novost(self):
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x"
        )
        assert "НОВОСТЬ" in html
        # the old redundant phrasing must be gone
        assert "корпоративном портале" not in html

    def test_eyebrow_uses_category_when_provided(self):
        html, text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x", category="Анонсы"
        )
        assert "АНОНСЫ" in html
        assert "Анонсы" in text

    def test_includes_cover_image_when_provided(self):
        cover = "https://portal.local/media/news/abc/cover.jpg?v=1"
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x", cover_url=cover
        )
        assert cover in html
        assert "<img" in html

    def test_omits_cover_image_when_none(self):
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x"
        )
        assert "<img" not in html

    def test_cover_is_clickable_link_to_news(self):
        link = "https://portal.local/news/42"
        html, _text = email_share.build_share_email_content(
            news_title="T",
            excerpt="E",
            news_link=link,
            cover_url="https://portal.local/media/news/abc/cover.jpg",
        )
        # the <img> must be wrapped in an <a> pointing at the news
        anchor = html[: html.index("<img")]
        assert f'<a href="{link}"' in anchor

    def test_cover_cid_takes_priority_over_url(self):
        html, _text = email_share.build_share_email_content(
            news_title="T",
            excerpt="E",
            news_link="http://x",
            cover_url="https://portal.local/media/news/abc/cover.jpg",
            cover_cid="cover-123",
        )
        assert 'src="cid:cover-123"' in html
        assert "media/news/abc/cover.jpg" not in html

    def test_uses_accent_color(self):
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x", accent_color="#0a7d33"
        )
        assert "#0a7d33" in html

    def test_mentions_office_or_vpn(self):
        html, text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x"
        )
        assert "корпоративный VPN" in html
        assert "корпоративный VPN" in text

    def test_includes_portal_url_when_provided(self):
        portal = "https://portal.local"
        html, text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x/news/1", portal_url=portal
        )
        assert portal in html
        assert portal in text

    def test_omits_portal_link_when_no_url(self):
        html, _text = email_share.build_share_email_content(
            news_title="T", excerpt="E", news_link="http://x/news/1"
        )
        assert "Открыть портал" not in html


# ── share_news_by_email ─────────────────────────────────────────────────────


class _FakeNested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fake_session() -> MagicMock:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=_FakeNested())
    return session


def _recipient(email: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email=email, name="R")


def _news() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), title="Заголовок", body="Тело новости")


def _actor() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email="editor@portal.local")


class TestShareNewsByEmail:
    @pytest.mark.asyncio
    async def test_enqueues_one_per_recipient(self):
        session = _fake_session()
        recipients = [_recipient("a@x.local"), _recipient("b@x.local")]
        enqueue = AsyncMock(return_value=uuid.uuid4())
        with (
            patch(f"{_SHARE}.enqueue_outbox_email", new=enqueue),
            patch(f"{_SHARE}.load_system_settings", return_value=MagicMock(portal_base_url="http://p")),
        ):
            n = await email_share.share_news_by_email(
                session, news=_news(), recipients=recipients, message=None, actor=_actor()
            )
        assert n == 2
        assert enqueue.await_count == 2
        emails = {c.kwargs["to_email"] for c in enqueue.await_args_list}
        assert emails == {"a@x.local", "b@x.local"}

    @pytest.mark.asyncio
    async def test_failed_recipient_isolated(self):
        session = _fake_session()
        recipients = [_recipient("ok@x.local"), _recipient("bad@x.local"), _recipient("ok2@x.local")]

        async def _enqueue(_session, **kwargs):
            if kwargs["to_email"] == "bad@x.local":
                raise RuntimeError("boom")
            return uuid.uuid4()

        with (
            patch(f"{_SHARE}.enqueue_outbox_email", side_effect=_enqueue),
            patch(f"{_SHARE}.load_system_settings", return_value=MagicMock(portal_base_url="http://p")),
        ):
            n = await email_share.share_news_by_email(
                session, news=_news(), recipients=recipients, message=None, actor=_actor()
            )
        assert n == 2

    @pytest.mark.asyncio
    async def test_embeds_inline_cover_when_present(self):
        session = _fake_session()
        news = SimpleNamespace(
            id=uuid.uuid4(),
            title="T",
            body="B",
            cover_image="abc/cover.jpg",
            updated_at=None,
            categories=["Анонсы"],
        )
        enqueue = AsyncMock(return_value=uuid.uuid4())
        with (
            patch(f"{_SHARE}.enqueue_outbox_email", new=enqueue),
            patch(
                f"{_SHARE}.load_system_settings",
                return_value=MagicMock(portal_base_url="http://p"),
            ),
            patch(f"{_SHARE}.build_email_cover_jpeg", return_value=b"\xff\xd8jpegbytes"),
        ):
            await email_share.share_news_by_email(
                session,
                news=news,
                recipients=[_recipient("a@x.local")],
                message=None,
                actor=_actor(),
            )
        kwargs = enqueue.await_args.kwargs
        payload = kwargs["payload"]
        assert payload["inline_images"][0]["cid"] == f"cover-{news.id}"
        assert payload["inline_images"][0]["mime"] == "image/jpeg"
        assert f'src="cid:cover-{news.id}"' in kwargs["body_html"]

    @pytest.mark.asyncio
    async def test_falls_back_to_remote_cover_when_embed_unavailable(self):
        session = _fake_session()
        news = SimpleNamespace(
            id=uuid.uuid4(),
            title="T",
            body="B",
            cover_image="abc/cover.jpg",
            updated_at=None,
            categories=[],
        )
        enqueue = AsyncMock(return_value=uuid.uuid4())
        with (
            patch(f"{_SHARE}.enqueue_outbox_email", new=enqueue),
            patch(
                f"{_SHARE}.load_system_settings",
                return_value=MagicMock(portal_base_url="http://p"),
            ),
            patch(f"{_SHARE}.build_email_cover_jpeg", return_value=None),
        ):
            await email_share.share_news_by_email(
                session,
                news=news,
                recipients=[_recipient("a@x.local")],
                message=None,
                actor=_actor(),
            )
        kwargs = enqueue.await_args.kwargs
        assert kwargs["payload"] is None
        assert "http://p/media/news/abc/cover.jpg" in kwargs["body_html"]

    @pytest.mark.asyncio
    async def test_custom_message_overrides_excerpt(self):
        session = _fake_session()
        enqueue = AsyncMock(return_value=uuid.uuid4())
        with (
            patch(f"{_SHARE}.enqueue_outbox_email", new=enqueue),
            patch(f"{_SHARE}.load_system_settings", return_value=MagicMock(portal_base_url="http://p")),
        ):
            await email_share.share_news_by_email(
                session,
                news=_news(),
                recipients=[_recipient("a@x.local")],
                message="Ручной текст",
                actor=_actor(),
            )
        body_html = enqueue.await_args.kwargs["body_html"]
        assert "Ручной текст" in body_html


# ── POST /news/{id}/share-email ─────────────────────────────────────────────

_NEWS_SVC = "app.api.news.routes.news_svc"
_RECIPIENTS_SVC = "app.api.news.routes.recipients_svc"
_SHARE_FN = "app.api.news.routes.share_news_by_email"
_AUDIT = "app.api.news.routes.emit_news_audit"


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), role=role, email=f"{role}@test.local", full_name="U", department="IT"
    )


def _build_app(user):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin, require_editor
    from app.api.news.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/news")

    async def _u():
        return user

    async def _db():
        return AsyncMock()

    async def _r():
        return AsyncMock()

    app.dependency_overrides[get_current_user] = _u
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _r
    app.dependency_overrides[require_editor] = _u
    app.dependency_overrides[require_admin] = _u
    return app


class TestShareNewsEmailEndpoint:
    @pytest.mark.asyncio
    async def test_published_ok(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app(user)
        news = SimpleNamespace(id=uuid.uuid4(), title="T", status="published", body="B")
        recipients = [SimpleNamespace(id=uuid.uuid4(), email="a@x.local", name="R")]
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch(f"{_RECIPIENTS_SVC}.resolve_recipients", new=AsyncMock(return_value=recipients)),
            patch(f"{_SHARE_FN}", new=AsyncMock(return_value=1)),
            patch(f"{_AUDIT}", new=AsyncMock()),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/news/{news.id}/share-email",
                    json={"recipient_ids": [str(recipients[0].id)]},
                )
        assert resp.status_code == 200
        assert resp.json()["enqueued"] == 1

    @pytest.mark.asyncio
    async def test_draft_returns_409(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app(user)
        news = SimpleNamespace(id=uuid.uuid4(), title="T", status="draft", body="B")
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/news/{news.id}/share-email",
                    json={"recipient_ids": [str(uuid.uuid4())]},
                )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_news_not_found_404(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app(user)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/news/{uuid.uuid4()}/share-email",
                    json={"recipient_ids": [str(uuid.uuid4())]},
                )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_recipient_ids_422(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app(user)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/news/{uuid.uuid4()}/share-email", json={"recipient_ids": []}
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_too_many_recipient_ids_422(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app(user)
        ids = [str(uuid.uuid4()) for _ in range(101)]
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/news/{uuid.uuid4()}/share-email", json={"recipient_ids": ids}
            )
        assert resp.status_code == 422


# ── build_email_cover_jpeg ──────────────────────────────────────────────────


class TestBuildEmailCoverJpeg:
    def test_returns_downscaled_jpeg(self, tmp_path):
        pil_image = pytest.importorskip("PIL.Image", reason="Pillow not installed locally")
        import io

        from app.services.news._helpers import build_email_cover_jpeg

        src = tmp_path / "cover.png"
        pil_image.new("RGB", (1200, 800), (10, 120, 240)).save(src)
        out = build_email_cover_jpeg(src, max_width=600)
        assert out is not None
        assert out[:2] == b"\xff\xd8"  # JPEG SOI magic
        with pil_image.open(io.BytesIO(out)) as result:
            assert result.width <= 600

    def test_flattens_transparency(self, tmp_path):
        pil_image = pytest.importorskip("PIL.Image", reason="Pillow not installed locally")
        from app.services.news._helpers import build_email_cover_jpeg

        src = tmp_path / "cover.png"
        pil_image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(src)
        out = build_email_cover_jpeg(src)
        assert out is not None
        assert out[:2] == b"\xff\xd8"

    def test_missing_source_returns_none(self, tmp_path):
        pytest.importorskip("PIL.Image", reason="Pillow not installed locally")
        from app.services.news._helpers import build_email_cover_jpeg

        assert build_email_cover_jpeg(tmp_path / "nope.png") is None
