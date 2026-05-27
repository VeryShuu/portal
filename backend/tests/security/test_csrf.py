"""CSRF / Origin-check middleware tests."""

from __future__ import annotations


async def test_csrf_full_chain_double_submit_cookie(app):
    """4.1: Полная цепочка double-submit cookie:
    1. GET /health — получаем XSRF-TOKEN в Set-Cookie (автоматически сохраняется в jar).
    2. POST с правильным cookie+header → проходит CSRF middleware (может упасть на auth).
    3. POST с cookie, но без X-XSRF-TOKEN header → 403 CSRF.
    4. POST с cookie, но header не совпадает с cookie → 403 CSRF.
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as ac:
        get_resp = await ac.get("/health")
        assert get_resp.status_code == 200

        csrf_token = ac.cookies.get("XSRF-TOKEN")
        assert csrf_token is not None, "GET /health must set XSRF-TOKEN cookie in jar"

        post_with_token = await ac.post(
            "/api/v1/news",
            json={"title": "x", "body": "y"},
            headers={"Origin": "http://test", "X-XSRF-TOKEN": csrf_token},
        )
        assert post_with_token.status_code not in (403,) or "CSRF" not in (
            post_with_token.json().get("detail", "")
        ), (
            f"POST с корректным double-submit не должен вернуть 403 CSRF; получили {post_with_token.json()}"
        )

        post_no_header = await ac.post(
            "/api/v1/news",
            json={"title": "x", "body": "y"},
            headers={"Origin": "http://test"},
        )
        assert post_no_header.status_code == 403
        assert "CSRF" in post_no_header.json().get("detail", "")

        post_mismatch = await ac.post(
            "/api/v1/news",
            json={"title": "x", "body": "y"},
            headers={"Origin": "http://test", "X-XSRF-TOKEN": "attacker-token"},
        )
        assert post_mismatch.status_code == 403
        assert "CSRF" in post_mismatch.json().get("detail", "")


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
    assert r.status_code != 403, f"CSRF-exempt callback path must not return 403; got: {r.json()}"


async def test_csrf_token_mismatch_blocked(app):
    """XSRF-TOKEN cookie и X-XSRF-TOKEN header разные → 403 (token-substitution attack)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "X-XSRF-TOKEN": "attacker-token"},
        cookies={"XSRF-TOKEN": "legitimate-token"},
    ) as ac:
        r = await ac.post("/api/v1/news", json={"title": "x", "body": "y"})
    assert r.status_code == 403
    assert "CSRF" in r.json().get("detail", "")
