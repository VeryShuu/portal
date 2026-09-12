"""Unit-тесты: ошибки в OIDC callback редиректят на /auth/error?reason=sso_failed
и пишут audit-event auth.sso_failed.

Тесты используют fakeredis из фикстуры `app` и моки kc_service / parse_jwt_claims.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_callback_error_only_without_code_redirects(client):
    """error=... без code (как шлёт Keycloak при отказе) → 302, не 422 (A2)."""
    resp = await client.get(
        "/api/v1/auth/callback",
        params={"error": "access_denied", "state": "y"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_missing_code_and_state_redirects(client):
    """Полностью пустой/битый callback → контролируемый 302, не 422 (A2)."""
    resp = await client.get(
        "/api/v1/auth/callback",
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
        "app.api.auth.oidc.kc_service.exchange_code_for_tokens",
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

    with (
        patch(
            "app.api.auth.oidc.kc_service.exchange_code_for_tokens",
            new=AsyncMock(return_value={"access_token": "at", "id_token": "it"}),
        ),
        patch(
            "app.api.auth.oidc.kc_service.get_jwks",
            new=AsyncMock(return_value={"keys": []}),
        ),
        patch(
            "app.api.auth.oidc.parse_jwt_claims",
            new=AsyncMock(side_effect=ValueError("bad jwt")),
        ),
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
    with (
        patch(
            "app.api.auth.oidc.kc_service.exchange_code_for_tokens",
            new=AsyncMock(return_value={"access_token": "at"}),
        ),
        patch(
            "app.api.auth.oidc.kc_service.get_jwks",
            new=AsyncMock(return_value={"keys": []}),
        ),
        patch(
            "app.api.auth.oidc.parse_jwt_claims",
            new=AsyncMock(return_value=fake_claims),
        ),
    ):
        resp = await client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "valid-state-3"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=sso_failed"


@pytest.mark.asyncio
async def test_callback_passes_full_name_to_link_guest_tickets(client, app):
    """Happy-path callback передаёт user.full_name в link_guest_tickets —
    чтобы гостевые email-заявки без display-name дозаполняли снимок имени
    для FTS (миграция 094). Регрессия: раньше full_name не передавался."""
    from types import SimpleNamespace

    from app.api.deps import get_db
    from app.services.session import save_pkce_state

    redis = app.state.redis
    await save_pkce_state(redis, "valid-state-fn", "verifier", "nonce-fn", "/")

    fake_user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        email="borisov@company.local",
        full_name="Иван Борисов",
        keycloak_id="kc-borisov",
        auth_source="keycloak",
    )

    # db-заглушка: _upsert_user и full_name-UPDATE выполняют db.execute без
    # бизнес-значения для этого теста (возвращаемые user/bool задаём через
    # mock _upsert_user напрямую).
    async def _fake_db():
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    app.dependency_overrides[get_db] = _fake_db

    link_mock = AsyncMock(return_value=0)
    fake_claims = {
        "sub": "kc-borisov",
        "email": "borisov@company.local",
        "name": "Иван Борисов",
        "nonce": "nonce-fn",
        "preferred_username": "borisov",
        "email_verified": True,
    }
    try:
        with (
            patch(
                "app.api.auth.oidc.kc_service.exchange_code_for_tokens",
                new=AsyncMock(
                    return_value={"access_token": "at", "id_token": "it", "refresh_token": "rt"}
                ),
            ),
            patch(
                "app.api.auth.oidc.kc_service.get_jwks",
                new=AsyncMock(return_value={"keys": []}),
            ),
            patch(
                "app.api.auth.oidc.parse_jwt_claims",
                new=AsyncMock(return_value=fake_claims),
            ),
            patch(
                "app.api.auth.oidc._resolve_id_token_nonce",
                new=AsyncMock(return_value="nonce-fn"),
            ),
            patch(
                "app.api.auth.oidc.get_full_name_attr_key_sa",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.auth.oidc._upsert_user",
                new=AsyncMock(return_value=(fake_user, False)),
            ),
            patch(
                "app.api.auth.oidc.rotate_session",
                new=AsyncMock(return_value="session-id"),
            ),
            patch(
                "app.api.auth.oidc.push_audit_event",
                new=AsyncMock(),
            ),
            patch(
                "app.services.helpdesk.tickets.link_guest_tickets",
                new=link_mock,
            ),
        ):
            resp = await client.get(
                "/api/v1/auth/callback",
                params={"code": "x", "state": "valid-state-fn"},
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 302
    # Ключевое: link_guest_tickets вызван с full_name пользователя.
    link_mock.assert_awaited_once()
    _, kwargs = link_mock.call_args
    assert kwargs["user_id"] == fake_user.id
    assert kwargs["email"] == "borisov@company.local"
    assert kwargs["full_name"] == "Иван Борисов"


@pytest.mark.asyncio
async def test_logout_get_redirects_to_auth_error(client):
    """GET /auth/logout без сессии → 302 на /auth/error?reason=logged_out."""
    resp = await client.get("/api/v1/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/error?reason=logged_out"
