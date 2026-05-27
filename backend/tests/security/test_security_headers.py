"""Security headers / TLS hardening checks (defense-in-depth).

Покрывается middleware `security_headers` из app/main.py.
"""

from __future__ import annotations


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


async def test_csp_header_not_set_by_backend(client):
    """Backend must NOT set Content-Security-Policy.

    Nginx is the single source of truth for CSP (with dynamic frame-src) and
    drops upstream copies via ``proxy_hide_header``. Setting CSP here too
    would cause duplicate headers when serving non-proxied responses in tests
    or when hitting the backend directly.
    """
    r = await client.get("/health")
    assert "Content-Security-Policy" not in r.headers


async def test_hsts_only_in_production(monkeypatch, app):
    """HSTS добавляется только в production (по дизайну middleware)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/health")
        assert "Strict-Transport-Security" not in r.headers


async def test_hsts_present_in_production(monkeypatch, app):
    """HSTS выставляется в production-окружении."""
    from httpx import ASGITransport, AsyncClient

    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "environment", "production")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        r = await ac.get("/health")
    hsts = r.headers.get("Strict-Transport-Security", "")
    assert hsts, "HSTS header must be present in production"
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


async def test_nginx_csp_frame_src_narrowed_with_nextcloud_url():
    """frame-src содержит конкретный NC-origin, а не открытый https:."""
    from app.services.nginx_config import _build_nginx_csp

    csp = _build_nginx_csp("https://nextcloud.company.local", "")

    assert "frame-src 'self' https://nextcloud.company.local" in csp
    assert "frame-src 'self' https:;" not in csp


async def test_nginx_csp_frame_src_fallback_self_only_without_nextcloud():
    """frame-src = 'self' только, если nextcloud_url не задан."""
    from app.services.nginx_config import _build_nginx_csp

    csp = _build_nginx_csp("", "")

    assert "frame-src 'self';" in csp
    assert "frame-src 'self' https:" not in csp


async def test_nginx_csp_frame_src_no_open_https_for_any_nc_url():
    """_build_nginx_csp никогда не выдаёт открытый frame-src https:."""
    from app.services.nginx_config import _build_nginx_csp

    for nc_url in ["", "https://nc.local", "http://nc.internal:8080"]:
        csp = _build_nginx_csp(nc_url, "")
        assert "frame-src 'self' https:;" not in csp, (
            f"Open scheme-wildcard frame-src https: found with nextcloud_url={nc_url!r}: {csp}"
        )
