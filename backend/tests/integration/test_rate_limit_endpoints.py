"""Integration: rate-limit на неавторизационных endpoints.

Покрывает endpoints с RateLimiter помимо /auth/local/login:
  - GET  /api/v1/search          (60 req/min)
  - GET  /api/v1/search/suggest  (120 req/min)
  - POST /api/v1/users/me/password (10 req/15min)
  - POST /api/v1/auth/refresh    (30 req/min)
"""

from __future__ import annotations

import contextlib

import pytest
import pytest_asyncio

from tests.conftest import _CSRF_TOKEN

pytestmark = pytest.mark.asyncio


def _csrf_kwargs(ip: str) -> dict:
    return {
        "headers": {
            "Origin": "http://test",
            "X-Real-IP": ip,
            "x-xsrf-token": _CSRF_TOKEN,
        },
        "cookies": {"XSRF-TOKEN": _CSRF_TOKEN},
    }


@pytest_asyncio.fixture
async def limiter(redis_client):
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    import tests.conftest as _root_conftest
    from app.core.limiter import real_ip_identifier

    saved_call = RateLimiter.__call__
    if _root_conftest._real_rate_limiter_call is not None:
        RateLimiter.__call__ = _root_conftest._real_rate_limiter_call  # type: ignore[method-assign]

    await FastAPILimiter.init(redis_client, identifier=real_ip_identifier)
    try:
        yield redis_client
    finally:
        RateLimiter.__call__ = saved_call  # type: ignore[method-assign]
        with contextlib.suppress(Exception):
            await FastAPILimiter.close()


async def _exhaust(ac, method: str, url: str, times: int, **kwargs) -> None:
    for _ in range(times):
        fn = getattr(ac, method)
        await fn(url, **kwargs)


async def test_search_rate_limit_blocks_after_60(limiter, app):
    """61-й запрос к /search с одного IP → 429."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.0.1")
    ) as ac:
        await _exhaust(ac, "get", "/api/v1/search", times=60, params={"q": "test"})
        r = await ac.get("/api/v1/search", params={"q": "test"})
        assert r.status_code == 429


async def test_search_suggest_rate_limit_blocks_after_120(limiter, app):
    """121-й запрос к /search/suggest с одного IP → 429."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.0.2")
    ) as ac:
        await _exhaust(ac, "get", "/api/v1/search/suggest", times=120, params={"q": "test"})
        r = await ac.get("/api/v1/search/suggest", params={"q": "test"})
        assert r.status_code == 429


async def test_auth_refresh_rate_limit_blocks_after_30(limiter, app):
    """31-й запрос к /auth/refresh с одного IP → 429."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.0.3")
    ) as ac:
        await _exhaust(ac, "post", "/api/v1/auth/refresh", times=30)
        r = await ac.post("/api/v1/auth/refresh")
        assert r.status_code == 429


async def test_password_change_rate_limit_blocks_after_10(limiter, app):
    """11-й запрос к /users/me/password с одного IP → 429.

    Endpoint требует авторизацию — 401 это нормальный ответ до блокировки.
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.0.4")
    ) as ac:
        for _ in range(10):
            r = await ac.patch(
                "/api/v1/users/me/password",
                json={"current_password": "old", "new_password": "newpass123"},
            )
            assert r.status_code in (401, 403, 422)

        r = await ac.patch(
            "/api/v1/users/me/password",
            json={"current_password": "old", "new_password": "newpass123"},
        )
        assert r.status_code == 429


async def test_different_ips_do_not_share_rate_limit(limiter, app):
    """Два разных IP независимы — каждый получает свою квоту."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.1.1")
    ) as ac1:
        await _exhaust(ac1, "get", "/api/v1/search", times=60, params={"q": "x"})
        r = await ac1.get("/api/v1/search", params={"q": "x"})
        assert r.status_code == 429

    async with AsyncClient(
        transport=transport, base_url="http://test", **_csrf_kwargs("10.9.1.2")
    ) as ac2:
        r = await ac2.get("/api/v1/search", params={"q": "x"})
        assert r.status_code != 429
