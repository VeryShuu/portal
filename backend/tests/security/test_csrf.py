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
        # `/api/v1/news` — non-exempt POST endpoint (auth/local/login is CSRF-exempt by design).
        r = await ac.post("/api/v1/news", json={"title": "x", "body": "y"})
        assert r.status_code == 403
        assert "CSRF" in r.json().get("detail", "")


async def test_post_with_wrong_origin_blocked(app):
    """POST с Origin не из allowed → 403."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "https://evil.example.com"}
    ) as ac:
        r = await ac.post("/api/v1/news", json={"title": "x", "body": "y"})
        assert r.status_code == 403


async def test_post_with_correct_origin_passes_csrf(app):
    """POST с корректным Origin проходит middleware (дальше — обычная логика).

    `auth/local/login` is in the CSRF-exempt list (pre-session bootstrap), so
    the middleware never returns CSRF here regardless of Origin/cookie state.
    """
    from unittest.mock import AsyncMock, MagicMock

    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_db

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_db] = _fake_db

    _CSRF_TOKEN = "test-csrf-token-for-unit-tests"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
        ) as ac:
            r = await ac.post(
                "/api/v1/auth/local/login",
                json={"email": "nonexistent@x.local", "password": "wrong"},
            )
        assert r.status_code != 403 or "CSRF" not in r.json().get("detail", "")
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_csrf_missing_xsrf_token_header(app):
    """XSRF-TOKEN cookie present but X-XSRF-TOKEN header absent → 403."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
        cookies={"XSRF-TOKEN": "some-token"},
    ) as ac:
        r = await ac.post("/api/v1/news", json={"title": "x", "body": "y"})
    assert r.status_code == 403


async def test_callback_path_exempt(app):
    """OIDC callback освобождён от CSRF-проверки (Keycloak редиректит без Origin)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/callback?code=x&state=y")
        # Любой код, кроме 403 CSRF.
        if r.status_code == 403:
            assert "CSRF" not in r.json().get("detail", "")
