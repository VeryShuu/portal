"""T1: API integration smoke tests через httpx.AsyncClient + ASGITransport.

Покрытие:
- /health всегда 200
- /auth/me 401 без сессии
- /auth/me 200 с replaced CurrentUser dependency (auth_source присутствует — P2-35)
- /auth/config возвращает local_auth_enabled
- /news 401 без сессии
- /news 200 с фильтрами category/is_pinned (P2-36)
- /news ?status=draft 403 для reader
- CSRF: POST без Origin → 403 (P1-15)

Локально пропускается без fastapi/httpx; в CI — выполняется в Docker.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally (CI runs in Docker)")
pytest.importorskip("httpx", reason="httpx not installed locally")

from httpx import ASGITransport, AsyncClient


def _make_user(role: str = "reader"):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@portal.local"
    user.full_name = "Test User"
    user.department = "IT"
    user.position = "Engineer"
    user.phone = None
    user.role = role
    user.avatar_url = None
    user.presence_status = "office"
    user.notify_email = True
    user.notify_inapp = True
    user.lang = "ru"
    user.preferences = {}
    user.auth_source = "local"
    return user


@pytest.fixture
def app(monkeypatch):
    """Build app with bootstrap admin disabled to avoid DB calls in lifespan."""
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")

    # Re-import to pick up env
    import importlib
    import app.main as main_mod
    importlib.reload(main_mod)
    return main_mod.app


@pytest.mark.asyncio
async def test_health_always_ok(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_auth_me_unauthenticated_401(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_returns_auth_source(app):
    """P2-35: /auth/me должен возвращать auth_source."""
    from app.api.deps import get_current_user
    user = _make_user("admin")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 200
    body = r.json()
    assert body["auth_source"] == "local"
    assert body["role"] == "admin"
    assert body["email"] == "admin@portal.local"


@pytest.mark.asyncio
async def test_auth_config_public(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/config")
    assert r.status_code == 200
    body = r.json()
    assert "local_auth_enabled" in body
    assert "keycloak_enabled" in body


@pytest.mark.asyncio
async def test_news_list_unauthenticated_401(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/news")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_news_list_with_filters(app):
    """P2-36: /news принимает category и is_pinned."""
    from app.api.deps import get_current_user
    from app.services import news as news_svc

    user = _make_user("reader")

    async def _fake_user():
        return user

    captured: dict = {}

    async def _fake_get_list(db, *, user, status_filter, page, page_size, category=None, is_pinned=None):
        captured["category"] = category
        captured["is_pinned"] = is_pinned
        captured["status_filter"] = status_filter
        return [], 0

    app.dependency_overrides[get_current_user] = _fake_user
    orig = news_svc.get_news_list
    news_svc.get_news_list = _fake_get_list  # type: ignore[assignment]
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/news?category=hr&is_pinned=true")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        news_svc.get_news_list = orig  # type: ignore[assignment]

    assert r.status_code == 200
    assert captured["category"] == "hr"
    assert captured["is_pinned"] is True


@pytest.mark.asyncio
async def test_news_draft_status_forbidden_for_reader(app):
    from app.api.deps import get_current_user
    user = _make_user("reader")

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/news?status=draft")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_csrf_blocks_post_without_origin(app):
    """P1-15: state-changing POST без Origin/Referer → 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/local/login", json={"email": "x", "password": "y"})
    assert r.status_code == 403
    assert "CSRF" in r.json().get("detail", "")
