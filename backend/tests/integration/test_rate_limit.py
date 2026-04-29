"""Integration: fastapi-limiter с реальным Redis.

Покрывает Phase 2.1 — rate limit 5 попыток / 15 мин для /auth/local/login.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def limiter_initialized(redis_client):
    from fastapi_limiter import FastAPILimiter

    from app.core.limiter import real_ip_identifier

    await FastAPILimiter.init(redis_client, identifier=real_ip_identifier)
    try:
        yield
    finally:
        try:
            await FastAPILimiter.close()
        except Exception:
            pass


async def test_local_login_rate_limit_blocks_after_5_attempts(limiter_initialized, app):
    """Шестая попытка локального логина в течение 15 мин с одного IP → 429."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    headers = {
        "Origin": "http://test",
        "X-Real-IP": "10.0.0.42",
    }

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        # 5 первых попыток должны вернуть 401 (неверный пароль), не 429
        for _ in range(5):
            r = await ac.post(
                "/api/v1/auth/local/login",
                json={"email": "nobody@portal.local", "password": "wrong"},
            )
            assert r.status_code in (401, 403)

        # 6-я попытка — должна быть заблокирована rate-limiter'ом
        r = await ac.post(
            "/api/v1/auth/local/login",
            json={"email": "nobody@portal.local", "password": "wrong"},
        )
        assert r.status_code == 429
