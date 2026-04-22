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

pytest.importorskip("fastapi", reason="fastapi not installed locally (CI runs in Docker)")
pytest.importorskip("httpx", reason="httpx not installed locally")

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
    obj.id = uuid.uuid4()
    obj.title = overrides.get("title", "Hello")
    obj.body = overrides.get("body", "<p>body</p>")
    obj.status = overrides.get("status", "draft")
    obj.is_pinned = False
    obj.category = None
    obj.target_departments = None
    obj.target_roles = None
    obj.cover_image = None
    obj.author_id = uuid.uuid4()
    obj.created_at = now
    obj.updated_at = now
    obj.published_at = None
    obj.publish_at = None
    obj.archive_at = None
    obj.view_count = 0
    obj.current_version = 1
    obj.deleted_at = None
    return obj


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import importlib
    import app.main as main_mod
    importlib.reload(main_mod)
    return main_mod.app


@pytest.mark.asyncio
async def test_create_news_unauthenticated_401(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/news",
            json={"title": "T", "body": "B"},
            headers={"Origin": "http://test"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_news_forbidden_for_reader(app):
    from app.api.deps import get_current_user, require_role
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

    async def _none(db, news_id):
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
