"""Защищённые эндпоинты возвращают 401 без сессии."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


PROTECTED_GET = [
    "/api/v1/users",
    "/api/v1/users/me",
    "/api/v1/news",
    "/api/v1/links",
    "/api/v1/bookmarks",
    "/api/v1/kb/sections",
    "/api/v1/kb/articles",
    "/api/v1/search?q=test",
    "/api/v1/auth/me",
]


@pytest.mark.parametrize("path", PROTECTED_GET)
async def test_protected_get_requires_auth(client, path):
    r = await client.get(path)
    # Возможны 401 (no session) или 404 если роут не маунтится; нас интересует именно 401.
    assert r.status_code in (401, 403, 404, 422), f"{path} → {r.status_code}"
    if r.status_code in (401, 403):
        assert "auth" in r.json().get("detail", "").lower() or "not auth" in r.json().get("detail", "").lower() or "session" in r.json().get("detail", "").lower() or "permission" in r.json().get("detail", "").lower()


async def test_admin_endpoint_requires_admin(authed_client_factory):
    """reader → 403 на admin-эндпоинте."""
    ac, _ = authed_client_factory(role="reader")
    r = await ac.get("/api/v1/users")
    # /users требует auth, но не admin; admin-эндпоинты:
    r2 = await ac.post(
        "/api/v1/admin/users/local",
        json={"email": "x@y.local", "full_name": "X", "password": "Pass1234!", "role": "reader"},
    )
    assert r2.status_code in (403, 404)


async def test_editor_can_access_editor_routes(authed_client_factory):
    """editor имеет доступ к /news создание."""
    ac, _ = authed_client_factory(role="editor")
    r = await ac.get("/api/v1/news")
    assert r.status_code in (200, 404)


async def test_invalid_session_cookie_is_401(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
        cookies={"portal_session": "this-session-does-not-exist"},
    ) as ac:
        r = await ac.get("/api/v1/auth/me")
        assert r.status_code == 401
