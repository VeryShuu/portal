"""CSRF / Origin-check middleware tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_does_not_require_origin(app):
    """Безопасные методы (GET/HEAD/OPTIONS) проходят без Origin/Referer."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
        assert r.status_code == 200


async def test_post_without_origin_blocked(app):
    """POST без Origin/Referer → 403."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/local/login", json={"email": "x@y.local", "password": "p"})
        assert r.status_code == 403
        assert "CSRF" in r.json().get("detail", "")


async def test_post_with_wrong_origin_blocked(app):
    """POST с Origin не из allowed → 403."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "https://evil.example.com"}
    ) as ac:
        r = await ac.post("/api/v1/auth/local/login", json={"email": "x@y.local", "password": "p"})
        assert r.status_code == 403


async def test_post_with_correct_origin_passes_csrf(client):
    """POST с корректным Origin проходит middleware (дальше — обычная логика)."""
    r = await client.post(
        "/api/v1/auth/local/login",
        json={"email": "nonexistent@x.local", "password": "wrong"},
    )
    assert r.status_code != 403 or "CSRF" not in r.json().get("detail", "")


async def test_callback_path_exempt(app):
    """OIDC callback освобождён от CSRF-проверки (Keycloak редиректит без Origin)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/callback?code=x&state=y")
        # Любой код, кроме 403 CSRF.
        if r.status_code == 403:
            assert "CSRF" not in r.json().get("detail", "")
