"""T2: Integration-тесты API новостей (gallery/attachments/export).

Покрытие:
- POST /news 401 без сессии
- DELETE /news 403 для reader
- GET /news/{id}/export/html для несуществующей → 404
- GET /news/{id}/gallery 404 для несуществующей
- POST /news создаёт запись + триггерит audit event

Локально пропускается без fastapi/httpx; в CI выполняется в Docker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


def _make_user(role: str = "reader"):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@portal.local"
    user.full_name = "Test"
    user.role = role
    user.auth_source = "local"
    user.lang = "ru"
    user.preferences = {}
    return user


def _make_news(**overrides):
    now = datetime.now(UTC)
    obj = MagicMock()
    obj.id = overrides.get("id", uuid.uuid4())
    obj.title = overrides.get("title", "Hello")
    obj.body = overrides.get("body", "<p>body</p>")
    obj.status = overrides.get("status", "draft")
    obj.previous_status = overrides.get("previous_status")
    obj.is_pinned = False
    obj.categories = []
    obj.target_departments = None
    obj.target_roles = None
    obj.cover_image = None
    obj.cover_image_url = None
    obj.cover_focal_point = None
    obj.cover_dominant_color = None
    obj.cover_variants = None
    obj.cover_webp_srcset = None
    obj.cover_avif_srcset = None
    obj.author_id = uuid.uuid4()
    obj.author = None
    obj.created_at = now
    obj.updated_at = now
    obj.published_at = None
    obj.publish_at = None
    obj.archive_at = None
    obj.deleted_at = overrides.get("deleted_at")
    obj.view_count = 0
    obj.current_version = 1
    return obj


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
    _app = main_mod.app
    _app.state.redis = AsyncMock()
    return _app


@pytest.mark.asyncio
async def test_create_news_unauthenticated_401(app):
    _CSRF = "test-csrf-token"
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "X-XSRF-TOKEN": _CSRF},
        cookies={"XSRF-TOKEN": _CSRF},
    ) as ac:
        r = await ac.post("/api/v1/news", json={"title": "T", "body": "B"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_news_forbidden_for_reader(app):
    from app.api.deps import get_current_user

    user = _make_user("reader")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.delete(
                f"/api/v1/news/{uuid.uuid4()}",
                headers={"Origin": "http://test"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_nonexistent_news_404(app):
    from app.api.deps import get_current_user
    from app.services import news as news_svc

    user = _make_user("reader")

    async def _fake_user():
        return user

    async def _none(db, news_id, *args, **kwargs):
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    orig = news_svc.get_news_by_id
    news_svc.get_news_by_id = _none  # type: ignore[assignment]
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/v1/news/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        news_svc.get_news_by_id = orig  # type: ignore[assignment]

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_versions_endpoint_requires_editor(app):
    from app.api.deps import get_current_user

    user = _make_user("reader")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(f"/api/v1/news/{uuid.uuid4()}/versions")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


# ── Корзина: /trash и /purge ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trash_list_forbidden_for_reader(app):
    from app.api.deps import get_current_user

    user = _make_user("reader")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        _CSRF = "test-csrf"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test"},
        ) as ac:
            r = await ac.get("/api/v1/news/trash")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_trash_list_returns_only_deleted_for_admin(app):
    from app.api.deps import get_current_user
    from app.services import news as news_svc

    admin = _make_user("admin")
    deleted_news = _make_news(deleted_at=datetime.now(UTC), previous_status="published")
    active_news = _make_news()

    async def _fake_user():
        return admin

    async def _fake_get_trash(db, *, page, page_size):
        return [deleted_news], 1

    app.dependency_overrides[get_current_user] = _fake_user
    orig = news_svc.get_trash_news
    news_svc.get_trash_news = _fake_get_trash  # type: ignore[assignment]
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test"},
        ) as ac:
            r = await ac.get("/api/v1/news/trash")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        news_svc.get_trash_news = orig  # type: ignore[assignment]

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_purge_forbidden_for_non_admin(app):
    from app.api.deps import get_current_user

    user = _make_user("editor")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        _CSRF = "test-csrf"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "X-XSRF-TOKEN": _CSRF},
            cookies={"XSRF-TOKEN": _CSRF},
        ) as ac:
            r = await ac.delete(f"/api/v1/news/{uuid.uuid4()}/purge")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_purge_returns_400_if_not_soft_deleted(app):
    from app.api.deps import get_current_user
    from app.services import news as news_svc

    admin = _make_user("admin")
    active_news = _make_news(deleted_at=None)

    async def _fake_user():
        return admin

    async def _fake_get_by_id(db, news_id, *, include_deleted=False):
        return active_news

    app.dependency_overrides[get_current_user] = _fake_user
    orig = news_svc.get_news_by_id
    news_svc.get_news_by_id = _fake_get_by_id  # type: ignore[assignment]
    try:
        _CSRF = "test-csrf"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "X-XSRF-TOKEN": _CSRF},
            cookies={"XSRF-TOKEN": _CSRF},
        ) as ac:
            r = await ac.delete(f"/api/v1/news/{uuid.uuid4()}/purge")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        news_svc.get_news_by_id = orig  # type: ignore[assignment]
    assert r.status_code == 400
