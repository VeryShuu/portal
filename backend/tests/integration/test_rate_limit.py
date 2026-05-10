"""Integration: fastapi-limiter с реальным Redis.

Покрывает:
  - IP-based rate limit: 5 попыток / 15 мин для /auth/local/login.
  - Email-based rate limit: 10 попыток / 15 мин с разных IP для одного email.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def limiter_initialized(redis_client):
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    from app.core.limiter import real_ip_identifier
    import tests.conftest as _root_conftest

    saved_call = RateLimiter.__call__
    if _root_conftest._real_rate_limiter_call is not None:
        RateLimiter.__call__ = _root_conftest._real_rate_limiter_call  # type: ignore[method-assign]

    await FastAPILimiter.init(redis_client, identifier=real_ip_identifier)
    try:
        yield
    finally:
        RateLimiter.__call__ = saved_call  # type: ignore[method-assign]
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


async def test_email_identifier_rate_limit_blocks_across_different_ips(limiter_initialized, app):
    """Email-based лимит: 10 попыток / 15 мин — блокирует одинаковый email даже с разных IP.

    Первые 10 запросов уходят с разных IP (обходят IP-лимит 5/15min),
    но 11-й с любого IP должен вернуть 429 из-за email-идентификатора.
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    target_email = "victim@portal.local"

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as ac:
        # Используем 10 разных IP чтобы обойти IP-лимит (5 req/IP)
        for i in range(10):
            ip = f"10.1.2.{i + 1}"
            r = await ac.post(
                "/api/v1/auth/local/login",
                json={"email": target_email, "password": "wrong"},
                headers={"X-Real-IP": ip},
            )
            assert r.status_code in (401, 403), (
                f"Request {i + 1} from {ip} expected 401/403, got {r.status_code}"
            )

        # 11-я попытка с новым IP — email-лимит исчерпан → 429
        r = await ac.post(
            "/api/v1/auth/local/login",
            json={"email": target_email, "password": "wrong"},
            headers={"X-Real-IP": "10.1.2.99"},
        )
        assert r.status_code == 429, f"Expected 429 from email limiter, got {r.status_code}"
