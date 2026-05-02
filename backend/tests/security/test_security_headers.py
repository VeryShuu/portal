"""Security headers / TLS hardening checks (defense-in-depth).

Покрывается middleware `security_headers` из app/main.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_security_headers_present(client):
    """Ответ /health отдаёт обязательные security-заголовки."""
    r = await client.get("/health")
    assert r.status_code == 200
    h = r.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("X-XSS-Protection") == "0"
    assert "strict-origin" in h.get("Referrer-Policy", "").lower()
    assert "camera=()" in h.get("Permissions-Policy", "")
    assert "microphone=()" in h.get("Permissions-Policy", "")
    assert "geolocation=()" in h.get("Permissions-Policy", "")


async def test_request_id_header_present(client):
    """Каждый ответ возвращает X-Request-Id."""
    r = await client.get("/health")
    assert "X-Request-Id" in r.headers
    rid = r.headers["X-Request-Id"]
    assert len(rid) >= 8


async def test_request_id_echoed_when_provided(client):
    rid = "11111111-2222-3333-4444-555555555555"
    r = await client.get("/health", headers={"X-Request-Id": rid})
    assert r.headers["X-Request-Id"] == rid


async def test_request_id_too_long_replaced(client):
    """Слишком длинный X-Request-Id не доверяется."""
    too_long = "a" * 200
    r = await client.get("/health", headers={"X-Request-Id": too_long})
    assert r.headers["X-Request-Id"] != too_long
    assert len(r.headers["X-Request-Id"]) <= 64


async def test_csp_header_present(client):
    r = await client.get("/health")
    csp = r.headers.get("Content-Security-Policy", "")
    assert csp, "Content-Security-Policy header must be present"
    assert "default-src" in csp
    assert "frame-src" in csp


async def test_hsts_only_in_production(monkeypatch, app):
    """HSTS добавляется только в production (по дизайну middleware)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/health")
        assert "Strict-Transport-Security" not in r.headers
