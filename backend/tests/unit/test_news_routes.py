"""Unit-тесты api/news/routes.py (Phase 4.9).

Покрытие:
- require_news_read_access: published ok / draft denied для reader
- GET /news: список / фильтрация статусов / ошибка 422 invalid status / 403 draft для reader
- GET /news/limits: возвращает лимиты
- GET /news/trash: список корзины (admin)
- GET /news/{id}: found / 404 / view dedup
- POST /news: 201 created / idempotency key
- PUT /news/{id}: success / 404
- DELETE /news/{id}: 204 / 404
- POST /news/{id}/restore: success / 400 not deleted
- DELETE /news/{id}/purge: success / 400 not deleted
- GET /news/{id}/versions: success / 404
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

_AUDIT_PATCH = "app.api.news._common.push_audit_event"
_NEWS_SVC = "app.api.news.routes.news_svc"


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name="Test User",
        department="IT",
    )


def _make_db() -> AsyncMock:
    return AsyncMock()


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _make_news(*, status: str = "published", deleted_at=None) -> MagicMock:
    news = MagicMock()
    news.id = uuid.uuid4()
    news.title = "Test News"
    news.body = "<p>Body</p>"
    news.status = status
    news.is_pinned = False
    news.categories = []
    news.cover_image = None
    news.cover_image_url = None
    news.cover_focal_point = None
    news.cover_dominant_color = None
    news.cover_variants = None
    news.cover_webp_srcset = None
    news.cover_avif_srcset = None
    news.target_departments = None
    news.target_roles = None
    news.author_id = None
    news.publish_at = None
    news.archive_at = None
    news.published_at = None
    news.deleted_at = deleted_at
    news.view_count = 0
    news.current_version = 1
    now = datetime.now(UTC)
    news.created_at = now
    news.updated_at = now
    return news


def _build_app(user, db, redis):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin, require_editor
    from app.api.news.routes import router

    _app = FastAPI()
    _app.include_router(router, prefix="/news")

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    _app.dependency_overrides[require_editor] = _fake_user
    _app.dependency_overrides[require_admin] = _fake_user
    return _app


# ── require_news_read_access ───────────────────────────────────────────────────


class TestRequireNewsReadAccess:
    def test_published_news_accessible_to_reader(self):

        from app.api.news._common import require_news_read_access

        news = _make_news(status="published")
        user = _make_user(role="reader")
        require_news_read_access(news, user)

    def test_draft_news_denied_to_reader(self):
        from fastapi import HTTPException

        from app.api.news._common import require_news_read_access

        news = _make_news(status="draft")
        user = _make_user(role="reader")
        with pytest.raises(HTTPException) as exc_info:
            require_news_read_access(news, user)
        assert exc_info.value.status_code == 403

    def test_draft_news_accessible_to_editor(self):
        from app.api.news._common import require_news_read_access

        news = _make_news(status="draft")
        user = _make_user(role="editor")
        require_news_read_access(news, user)

    def test_archived_news_denied_to_reader(self):
        from fastapi import HTTPException

        from app.api.news._common import require_news_read_access

        news = _make_news(status="archived")
        user = _make_user(role="reader")
        with pytest.raises(HTTPException) as exc_info:
            require_news_read_access(news, user)
        assert exc_info.value.status_code == 403


# ── GET /news ──────────────────────────────────────────────────────────────────


class TestListNews:
    @pytest.mark.asyncio
    async def test_returns_news_list(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        news = _make_news()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_list", new=AsyncMock(return_value=([news], 1))):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/news")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_list", new=AsyncMock(return_value=([], 0))):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/news?status=invalid_status")

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_draft_filter_forbidden_for_reader(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="reader")
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_list", new=AsyncMock(return_value=([], 0))):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/news?status=draft")

        assert resp.status_code == 403


# ── GET /news/limits ───────────────────────────────────────────────────────────


class TestGetNewsLimits:
    @pytest.mark.asyncio
    async def test_returns_limits(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        fake_settings = MagicMock()
        fake_settings.news_attachment_max_size_mb = 10

        app = _build_app(user, db, redis)
        with patch("app.api.news.routes.load_system_settings", return_value=fake_settings):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/news/limits")

        assert resp.status_code == 200
        assert resp.json()["news_attachment_max_size_mb"] == 10


# ── GET /news/{id} ─────────────────────────────────────────────────────────────


class TestGetNews:
    @pytest.mark.asyncio
    async def test_returns_news(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        news = _make_news()
        redis.exists = AsyncMock(return_value=True)
        redis.setex = AsyncMock()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/news/{news.id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(news.id)

    @pytest.mark.asyncio
    async def test_increments_view_count_once(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        news = _make_news()
        redis.exists = AsyncMock(return_value=False)
        redis.setex = AsyncMock()

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch(f"{_NEWS_SVC}.increment_view_count", new=AsyncMock()) as mock_incr,
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get(f"/news/{news.id}")
            mock_incr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_on_missing(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/news/{uuid.uuid4()}")

        assert resp.status_code == 404


# ── POST /news ─────────────────────────────────────────────────────────────────


class TestCreateNews:
    @pytest.mark.asyncio
    async def test_creates_and_returns_201(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()
        news = _make_news()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        body = {
            "title": "Test News",
            "body": "<p>Body</p>",
            "status": "draft",
            "categories": [],
        }

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.create_news", new=AsyncMock(return_value=news)),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch("app.api.news.routes.ensure_category_exists"),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/news", json=body)

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_idempotency_key_returns_cached(self):
        import httpx
        from httpx import ASGITransport

        from app.schemas.news import NewsPublic

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()
        news = _make_news()
        public = NewsPublic.model_validate(news)
        redis.get = AsyncMock(return_value=public.model_dump_json())

        body = {
            "title": "Test News",
            "body": "<p>Body</p>",
            "status": "draft",
            "categories": [],
        }

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.create_news", new=AsyncMock()) as mock_create:
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/news",
                    json=body,
                    headers={"Idempotency-Key": "test-key"},
                )
            mock_create.assert_not_awaited()

        assert resp.status_code == 201


# ── PUT /news/{id} ─────────────────────────────────────────────────────────────


class TestUpdateNews:
    @pytest.mark.asyncio
    async def test_updates_news(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()
        news = _make_news()

        body = {"title": "Updated Title", "body": "<p>Updated</p>", "categories": []}

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch(f"{_NEWS_SVC}.update_news", new=AsyncMock(return_value=news)),
            patch(_AUDIT_PATCH, new=AsyncMock()),
            patch("app.api.news.routes.ensure_category_exists"),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(f"/news/{news.id}", json=body)

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_404_on_missing(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()

        body = {"title": "Title", "body": "<p>Body</p>", "categories": []}

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(f"/news/{uuid.uuid4()}", json=body)

        assert resp.status_code == 404


# ── DELETE /news/{id} ──────────────────────────────────────────────────────────


class TestDeleteNews:
    @pytest.mark.asyncio
    async def test_deletes_news_returns_204(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()
        news = _make_news()

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch(f"{_NEWS_SVC}.delete_news", new=AsyncMock()),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(f"/news/{news.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_404_on_missing(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(f"/news/{uuid.uuid4()}")

        assert resp.status_code == 404


# ── POST /news/{id}/restore ────────────────────────────────────────────────────


class TestRestoreNews:
    @pytest.mark.asyncio
    async def test_restores_deleted_news(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        deleted_news = _make_news(deleted_at=datetime.now(UTC))
        restored_news = _make_news()

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=deleted_news)),
            patch(f"{_NEWS_SVC}.restore_news", new=AsyncMock(return_value=restored_news)),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/news/{deleted_news.id}/restore")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_400_when_not_deleted(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        not_deleted = _make_news(deleted_at=None)

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=not_deleted)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/news/{not_deleted.id}/restore")

        assert resp.status_code == 400


# ── DELETE /news/{id}/purge ────────────────────────────────────────────────────


class TestPurgeNews:
    @pytest.mark.asyncio
    async def test_purges_deleted_news(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        deleted_news = _make_news(deleted_at=datetime.now(UTC))

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=deleted_news)),
            patch(f"{_NEWS_SVC}.purge_news", new=AsyncMock()),
            patch(_AUDIT_PATCH, new=AsyncMock()),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(f"/news/{deleted_news.id}/purge")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_400_when_not_deleted(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        not_deleted = _make_news(deleted_at=None)

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=not_deleted)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete(f"/news/{not_deleted.id}/purge")

        assert resp.status_code == 400


# ── GET /news/{id}/versions ────────────────────────────────────────────────────


class TestGetVersions:
    @pytest.mark.asyncio
    async def test_returns_versions(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()
        news = _make_news()

        version = MagicMock()
        version.id = uuid.uuid4()
        version.news_id = news.id
        version.version = 1
        version.title = "Title v1"
        version.body = "<p>Body</p>"
        version.editor_id = uuid.uuid4()
        version.created_at = datetime.now(UTC)

        app = _build_app(user, db, redis)
        with (
            patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=news)),
            patch(f"{_NEWS_SVC}.get_news_versions", new=AsyncMock(return_value=[version])),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/news/{news.id}/versions")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_404_for_missing_news(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="editor")
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_news_by_id", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/news/{uuid.uuid4()}/versions")

        assert resp.status_code == 404


# ── GET /news/trash ────────────────────────────────────────────────────────────


class TestListTrashNews:
    @pytest.mark.asyncio
    async def test_returns_trash_list(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        deleted_news = _make_news(deleted_at=datetime.now(UTC))
        deleted_news.author = None
        deleted_news.previous_status = None

        app = _build_app(user, db, redis)
        with patch(f"{_NEWS_SVC}.get_trash_news", new=AsyncMock(return_value=([deleted_news], 1))):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/news/trash")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
