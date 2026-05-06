"""Unit-тесты: ошибки в OIDC callback редиректят на /auth/error?reason=sso_failed
и пишут audit-event auth.sso_failed.

Тесты используют fakeredis из фикстуры `app` и моки kc_service / parse_jwt_claims.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_callback_with_oidc_error_redirects_to_auth_error(client):
    """error=... от Keycloak → 302 на /auth/error?reason=sso_failed."""
    resp = await client.get(
        "/api/v1/auth/callback",
        params={"code": "x", "state": "y", "error": "login_required"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_with_invalid_state_redirects(client):
    """Неизвестный state (нет PKCE в Redis) → 302 на /auth/error?reason=sso_failed."""
    resp = await client.get(
        "/api/v1/auth/callback",
        params={"code": "x", "state": "unknown-state"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_token_exchange_failure_redirects(client, app):
    """Сбой exchange_code_for_tokens → 302 на /auth/error?reason=sso_failed."""
    # Сохраняем валидный PKCE-стейт в fakeredis, чтобы дойти до token-exchange.
    redis = app.state.redis
    from app.services.session import save_pkce_state

    await save_pkce_state(redis, "valid-state", "verifier", "nonce-x", "/")

    with patch(
        "app.api.auth.kc_service.exchange_code_for_tokens",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        resp = await client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "valid-state"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_jwt_parse_failure_redirects(client, app):
    """Сбой parse_jwt_claims → 302 на /auth/error?reason=sso_failed."""
    redis = app.state.redis
    from app.services.session import save_pkce_state

    await save_pkce_state(redis, "valid-state-2", "verifier", "nonce-y", "/")

    with patch(
        "app.api.auth.kc_service.exchange_code_for_tokens",
        new=AsyncMock(return_value={"access_token": "at", "id_token": "it"}),
    ), patch(
        "app.api.auth.kc_service.get_jwks",
        new=AsyncMock(return_value={"keys": []}),
    ), patch(
        "app.api.auth.parse_jwt_claims",
        new=AsyncMock(side_effect=ValueError("bad jwt")),
    ):
        resp = await client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "valid-state-2"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_nonce_mismatch_redirects(client, app):
    """Nonce mismatch → 302 на /auth/error?reason=sso_failed."""
    redis = app.state.redis
    from app.services.session import save_pkce_state

    await save_pkce_state(redis, "valid-state-3", "verifier", "expected-nonce", "/")

    fake_claims = {
        "sub": "kc-123",
        "email": "x@x.local",
        "name": "X",
        "nonce": "WRONG-NONCE",
        "preferred_username": "x",
    }
    with patch(
        "app.api.auth.kc_service.exchange_code_for_tokens",
        new=AsyncMock(return_value={"access_token": "at"}),
    ), patch(
        "app.api.auth.kc_service.get_jwks",
        new=AsyncMock(return_value={"keys": []}),
    ), patch(
        "app.api.auth.parse_jwt_claims",
        new=AsyncMock(return_value=fake_claims),
    ):
        resp = await client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "valid-state-3"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_logout_get_redirects_to_auth_error(client):
    """GET /auth/logout без сессии → 302 на /auth/error?reason=logged_out."""
    resp = await client.get("/api/v1/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=logged_out"
