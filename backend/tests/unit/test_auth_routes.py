"""Unit-тесты для app/api/auth.py — не покрытые существующими тестами части.

Покрытие:
- _nz: None / пустая строка / strip / список / другое значение
- _client_ip: с client / без client
- _callback_uri: использует portal_base_url
- _build_session_cookie_response: set-cookie header, redirect URL
- _resolve_id_token_nonce: без id_token / с nonce / без nonce fallback / ошибка parse
- GET /auth/config: local_auth_enabled flag
- GET /auth/me: поля пользователя
- POST /auth/logout: keycloak-source / local-source + audit + delete-cookie
- POST /auth/local/login: disabled / user not found / bad password / success
- POST /auth/refresh: no session cookie / no refresh_token / refresh error / success
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── _nz ───────────────────────────────────────────────────────────────────────


class TestNz:
    def test_none_returns_none(self):
        from app.api.auth import _nz

        assert _nz(None) is None

    def test_empty_string_returns_none(self):
        from app.api.auth import _nz

        assert _nz("") is None

    def test_whitespace_string_returns_none(self):
        from app.api.auth import _nz

        assert _nz("   ") is None

    def test_non_empty_string_stripped(self):
        from app.api.auth import _nz

        assert _nz("  hello  ") == "hello"

    def test_non_empty_string_returned(self):
        from app.api.auth import _nz

        assert _nz("value") == "value"

    def test_empty_list_returns_none(self):
        from app.api.auth import _nz

        assert _nz([]) is None

    def test_non_empty_list_returned(self):
        from app.api.auth import _nz

        assert _nz(["a", "b"]) == ["a", "b"]

    def test_other_type_returned_as_is(self):
        from app.api.auth import _nz

        assert _nz(42) == 42
        assert _nz(True) is True


# ── _client_ip ────────────────────────────────────────────────────────────────


class TestClientIp:
    def test_returns_host_when_client_present(self):
        from app.api.auth import _client_ip

        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "192.168.1.100"

        assert _client_ip(request) == "192.168.1.100"

    def test_returns_none_when_no_client(self):
        from app.api.auth import _client_ip

        request = MagicMock()
        request.client = None

        assert _client_ip(request) is None


# ── _callback_uri ─────────────────────────────────────────────────────────────


class TestCallbackUri:
    def test_builds_uri_from_base_url(self):
        from app.api.auth import _callback_uri

        with patch("app.api.auth._helpers.load_system_settings") as mock_settings:
            mock_settings.return_value = MagicMock(portal_base_url="https://portal.example.com")
            uri = _callback_uri()

        assert uri == "https://portal.example.com/api/v1/auth/callback"


# ── _build_session_cookie_response ────────────────────────────────────────────


class TestBuildSessionCookieResponse:
    def test_returns_redirect_with_cookie(self):
        from app.api.auth import _build_session_cookie_response

        resp = _build_session_cookie_response("/dashboard", "my-session-id")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"
        set_cookie = resp.headers.get("set-cookie", "")
        assert "portal_session=my-session-id" in set_cookie or "portal_session" in set_cookie

    def test_sets_last_auth_method_keycloak_cookie(self):
        """ADR-036 п.7: OIDC-логин маркирует способ входа как 'keycloak'.

        Фронт читает её на холодном старте, чтобы при истечении сессии уйти на
        корректный экран входа (а не на /auth/local для keycloak-юзера).
        """
        from app.api.auth import _build_session_cookie_response

        resp = _build_session_cookie_response("/", "sid")
        # Cookie читается фронтендом через document.cookie → НЕ HttpOnly.
        set_cookie_headers = resp.headers.getlist("set-cookie")
        method_cookie = [h for h in set_cookie_headers if h.startswith("portal_auth_method=")]
        assert method_cookie, "portal_auth_method cookie должна ставиться при OIDC-логине"
        assert "portal_auth_method=keycloak" in method_cookie[0]
        # httponly флаг не должен присутствовать (фронт читает напрямую).
        assert "httponly" not in method_cookie[0].lower()


# ── _resolve_id_token_nonce ───────────────────────────────────────────────────


class TestResolveIdTokenNonce:
    @pytest.mark.asyncio
    async def test_no_id_token_returns_fallback(self):
        from app.api.auth import _resolve_id_token_nonce

        result = await _resolve_id_token_nonce({}, {}, "fallback-nonce")
        assert result == "fallback-nonce"

    @pytest.mark.asyncio
    async def test_id_token_nonce_returned(self):
        from app.api.auth import _resolve_id_token_nonce

        with patch(
            "app.api.auth._helpers.parse_jwt_claims",
            new=AsyncMock(return_value={"nonce": "from-id-token"}),
        ):
            result = await _resolve_id_token_nonce(
                {"id_token": "raw-token"}, {"keys": []}, "fallback"
            )

        assert result == "from-id-token"

    @pytest.mark.asyncio
    async def test_id_token_parse_error_uses_fallback(self):
        from app.api.auth import _resolve_id_token_nonce

        with patch(
            "app.api.auth._helpers.parse_jwt_claims",
            new=AsyncMock(side_effect=ValueError("bad jwt")),
        ):
            result = await _resolve_id_token_nonce({"id_token": "bad"}, {}, "safe-fallback")

        assert result == "safe-fallback"

    @pytest.mark.asyncio
    async def test_no_nonce_in_id_token_uses_fallback(self):
        from app.api.auth import _resolve_id_token_nonce

        with patch(
            "app.api.auth._helpers.parse_jwt_claims",
            new=AsyncMock(return_value={"sub": "someone"}),
        ):
            result = await _resolve_id_token_nonce({"id_token": "token"}, {}, "fallback-nonce")

        assert result == "fallback-nonce"


# ── GET /auth/config ──────────────────────────────────────────────────────────


class TestAuthConfig:
    @pytest.mark.asyncio
    async def test_returns_config_dict(self, client):
        resp = await client.get("/api/v1/auth/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "local_auth_enabled" in data
        assert data["keycloak_enabled"] is True

    @pytest.mark.asyncio
    async def test_local_auth_enabled_true(self, client, monkeypatch):
        monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")
        resp = await client.get("/api/v1/auth/config")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_last_auth_method_null_when_no_cookie(self, app):
        """ADR-036 п.7: нет cookie `portal_auth_method` → last_auth_method=null
        (новое устройство / чистый браузер; фронт остаётся на дефолте keycloak)."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/auth/config")
        assert resp.status_code == 200
        assert resp.json()["last_auth_method"] is None

    @pytest.mark.asyncio
    async def test_last_auth_method_local_from_cookie(self, app):
        """Cookie `portal_auth_method=local` отражается в ответе /auth/config —
        фронт использует это на холодном старте, чтобы знать тип прошлой сессии."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"portal_auth_method": "local"},
        ) as ac:
            resp = await ac.get("/api/v1/auth/config")
        assert resp.status_code == 200
        assert resp.json()["last_auth_method"] == "local"

    @pytest.mark.asyncio
    async def test_last_auth_method_keycloak_from_cookie(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"portal_auth_method": "keycloak"},
        ) as ac:
            resp = await ac.get("/api/v1/auth/config")
        assert resp.status_code == 200
        assert resp.json()["last_auth_method"] == "keycloak"

    @pytest.mark.asyncio
    async def test_last_auth_method_invalid_cookie_value_returns_null(self, app):
        """Подделанное/битое значение cookie не должно влиять на контракт."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"portal_auth_method": "evil"},
        ) as ac:
            resp = await ac.get("/api/v1/auth/config")
        assert resp.status_code == 200
        assert resp.json()["last_auth_method"] is None


# ── GET /auth/me ──────────────────────────────────────────────────────────────


class TestAuthMe:
    @pytest.mark.asyncio
    async def test_returns_user_fields(self, authed_client_factory):
        user_id = uuid.uuid4()
        ac, _user = authed_client_factory(
            role="admin",
            id=user_id,
            email="admin@test.local",
            full_name="Test Admin",
            department="IT",
        )
        async with ac:
            resp = await ac.get("/api/v1/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user_id)
        assert data["email"] == "admin@test.local"
        assert data["role"] == "admin"
        assert "preferences" in data


# ── POST /auth/logout ─────────────────────────────────────────────────────────


class TestAuthLogout:
    @pytest.mark.asyncio
    async def test_keycloak_user_redirects_to_error_page(self, authed_client_factory, app):
        ac, _user = authed_client_factory(role="reader", auth_source="keycloak")

        with (
            patch(
                "app.api.auth.logout.get_session_from_request",
                new=AsyncMock(return_value={"auth_source": "keycloak"}),
            ),
            patch("app.api.auth.logout.delete_session", new=AsyncMock()),
            patch("app.api.auth.logout.push_audit_event", new=AsyncMock()),
        ):
            async with ac:
                resp = await ac.post("/api/v1/auth/logout", follow_redirects=False)

        assert resp.status_code == 302
        assert "logged_out" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_local_user_redirects_to_local_auth(self, authed_client_factory, app):
        ac, _user = authed_client_factory(role="reader", auth_source="local")

        with (
            patch(
                "app.api.auth.logout.get_session_from_request",
                new=AsyncMock(return_value={"auth_source": "local"}),
            ),
            patch("app.api.auth.logout.delete_session", new=AsyncMock()),
            patch("app.api.auth.logout.push_audit_event", new=AsyncMock()),
        ):
            async with ac:
                resp = await ac.post("/api/v1/auth/logout", follow_redirects=False)

        assert resp.status_code == 302
        assert "local" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_preserves_last_auth_method_cookie(self, authed_client_factory, app):
        """ADR-036 п.7: logout удаляет только portal_session, но НЕ portal_auth_method.

        Маркер способа входа должен пережить logout, чтобы после logout локальный
        юзер при следующем входе снова попал на /auth/local (а не на SSO).
        """
        ac, _user = authed_client_factory(role="reader", auth_source="local")

        with (
            patch(
                "app.api.auth.logout.get_session_from_request",
                new=AsyncMock(return_value={"auth_source": "local"}),
            ),
            patch("app.api.auth.logout.delete_session", new=AsyncMock()),
            patch("app.api.auth.logout.push_audit_event", new=AsyncMock()),
        ):
            async with ac:
                resp = await ac.post("/api/v1/auth/logout", follow_redirects=False)

        # Ни одна Set-Cookie не должна удалять portal_auth_method
        # (delete_cookie шлёт 'portal_auth_method=; Max-Age=0; ...').
        set_cookie_headers = resp.headers.get_list("set-cookie")
        for header in set_cookie_headers:
            assert (
                not header.startswith("portal_auth_method=") or "max-age=0" not in header.lower()
            ), f"portal_auth_method не должна удаляться при logout, получено: {header}"

    @pytest.mark.asyncio
    async def test_clears_session_cookie(self, authed_client_factory):
        ac, _user = authed_client_factory(role="reader")

        with (
            patch("app.api.auth.logout.get_session_from_request", new=AsyncMock(return_value={})),
            patch("app.api.auth.logout.delete_session", new=AsyncMock()),
            patch("app.api.auth.logout.push_audit_event", new=AsyncMock()),
        ):
            async with ac:
                resp = await ac.post("/api/v1/auth/logout", follow_redirects=False)

        set_cookie = resp.headers.get("set-cookie", "")
        assert "portal_session" in set_cookie or resp.status_code == 302


# ── POST /auth/local/login ────────────────────────────────────────────────────


class TestLocalLogin:
    @pytest.mark.asyncio
    async def test_disabled_returns_403(self, client, monkeypatch):
        monkeypatch.setenv("LOCAL_AUTH_ENABLED", "false")
        from app.core.config import get_settings

        get_settings.cache_clear()

        with patch("app.api.auth.local.settings") as mock_settings:
            mock_settings.local_auth_enabled = False
            mock_settings.is_production = False
            resp = await client.post(
                "/api/v1/auth/local/login",
                json={"email": "user@test.local", "password": "pass"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_not_found_returns_401(self, client, app):
        from app.api.deps import get_db

        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        async def _fake_db():
            return db

        app.dependency_overrides[get_db] = _fake_db

        try:
            with patch("app.api.auth.local.settings") as mock_settings:
                mock_settings.local_auth_enabled = True
                mock_settings.is_production = False
                with patch(
                    "app.api.auth.local.verify_password_async", new=AsyncMock(return_value=False)
                ):
                    resp = await client.post(
                        "/api/v1/auth/local/login",
                        json={"email": "nobody@test.local", "password": "wrong"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(self, client, app):

        from app.api.deps import get_db

        fake_user = SimpleNamespace(
            id=uuid.uuid4(),
            email="user@test.local",
            auth_source="local",
            password_hash="hashed",
        )

        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_user
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        async def _fake_db():
            return db

        app.dependency_overrides[get_db] = _fake_db

        try:
            with patch("app.api.auth.local.settings") as mock_settings:
                mock_settings.local_auth_enabled = True
                mock_settings.is_production = False
                with patch(
                    "app.api.auth.local.verify_password_async", new=AsyncMock(return_value=False)
                ):
                    resp = await client.post(
                        "/api/v1/auth/local/login",
                        json={"email": "user@test.local", "password": "wrong"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_successful_login_returns_200_with_cookie(self, client, app):
        from app.api.deps import get_db

        fake_user = SimpleNamespace(
            id=uuid.uuid4(),
            email="user@test.local",
            auth_source="local",
            password_hash="hashed",
        )

        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_user
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        async def _fake_db():
            return db

        app.dependency_overrides[get_db] = _fake_db

        try:
            with patch("app.api.auth.local.settings") as mock_settings:
                mock_settings.local_auth_enabled = True
                mock_settings.is_production = False
                with (
                    patch(
                        "app.api.auth.local.verify_password_async", new=AsyncMock(return_value=True)
                    ),
                    patch("app.api.auth.local.save_session", new=AsyncMock()),
                    patch("app.api.auth.local.push_audit_event", new=AsyncMock()),
                ):
                    resp = await client.post(
                        "/api/v1/auth/local/login",
                        json={"email": "user@test.local", "password": "correct"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        set_cookie = resp.headers.get("set-cookie", "")
        assert "portal_session" in set_cookie

    @pytest.mark.asyncio
    async def test_successful_login_sets_last_auth_method_cookie(self, client, app):
        """ADR-036 п.7: локальный логин маркирует cookie portal_auth_method=local.

        Без этого фронт на холодном старте не знает тип прошлой сессии и при
        истечении Redis-сессии редиректит локального юзера на Keycloak SSO.
        """
        from app.api.deps import get_db

        fake_user = SimpleNamespace(
            id=uuid.uuid4(),
            email="user@test.local",
            auth_source="local",
            password_hash="hashed",
        )

        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_user
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        async def _fake_db():
            return db

        app.dependency_overrides[get_db] = _fake_db

        try:
            with patch("app.api.auth.local.settings") as mock_settings:
                mock_settings.local_auth_enabled = True
                mock_settings.is_production = False
                with (
                    patch(
                        "app.api.auth.local.verify_password_async", new=AsyncMock(return_value=True)
                    ),
                    patch("app.api.auth.local.save_session", new=AsyncMock()),
                    patch("app.api.auth.local.push_audit_event", new=AsyncMock()),
                ):
                    resp = await client.post(
                        "/api/v1/auth/local/login",
                        json={"email": "user@test.local", "password": "correct"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        set_cookie_headers = resp.headers.get_list("set-cookie")
        method_cookie = [h for h in set_cookie_headers if h.startswith("portal_auth_method=")]
        assert method_cookie, "portal_auth_method должна ставиться при локальном логине"
        assert "portal_auth_method=local" in method_cookie[0]
        # Фронт читает через document.cookie → НЕ HttpOnly.
        assert "httponly" not in method_cookie[0].lower()
        # Долгоживущая (30 дней) — иначе знание теряется между сессиями.
        assert "max-age=2592000" in method_cookie[0].lower()


# ── POST /auth/refresh ────────────────────────────────────────────────────────


class TestAuthRefresh:
    @pytest.mark.asyncio
    async def test_no_refresh_token_in_session_returns_401(self, authed_client_factory, app):
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        with patch("app.api.auth.me.get_session", new=AsyncMock(return_value={})):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "old-session-id"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_kc_refresh_error_returns_401(self, authed_client_factory, app):
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        with (
            patch(
                "app.api.auth.me.get_session",
                new=AsyncMock(return_value={"refresh_token": "old-rt"}),
            ),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(side_effect=Exception("token expired")),
            ),
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "old-session-id"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_successful_refresh_returns_ok(self, authed_client_factory, app):
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        new_tokens = {"access_token": "new-at", "refresh_token": "new-rt"}

        with (
            patch(
                "app.api.auth.me.get_session",
                new=AsyncMock(return_value={"refresh_token": "old-rt"}),
            ),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(return_value=new_tokens),
            ),
            patch("app.api.auth.me.save_session", new=AsyncMock()),
            patch("app.api.auth.me.delete_session", new=AsyncMock()),
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={
                    "XSRF-TOKEN": _CSRF_TOKEN,
                    SESSION_COOKIE_NAME: "old-session-id",
                },
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_no_session_cookie_returns_401(self, authed_client_factory, app):
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from tests.conftest import _CSRF_TOKEN

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
        ) as client2:
            resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_deleted_user_returns_401(self, authed_client_factory, app):
        from datetime import UTC, datetime

        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=datetime.now(UTC))
        from app.core.security import SESSION_COOKIE_NAME

        with patch("app.api.auth.me.delete_session", new=AsyncMock()):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "old-session-id"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_without_new_refresh_token(self, authed_client_factory, app):
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        new_tokens = {"access_token": "new-at"}

        with (
            patch(
                "app.api.auth.me.get_session",
                new=AsyncMock(return_value={"refresh_token": "old-rt"}),
            ),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(return_value=new_tokens),
            ),
            patch("app.api.auth.me.save_session", new=AsyncMock()),
            patch("app.api.auth.me.delete_session", new=AsyncMock()),
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={
                    "XSRF-TOKEN": _CSRF_TOKEN,
                    SESSION_COOKIE_NAME: "old-session-id",
                },
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_recent_refresh_is_coalesced_without_keycloak(self, authed_client_factory, app):
        """Если сессию обновили только что (refreshed_at в окне), вкладка-ждун
        не должна дёргать Keycloak повторно — просто возвращает ok."""
        import time

        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        fresh_session = {
            "refresh_token": "rt",
            "access_token": "at",
            "refreshed_at": time.time(),
        }
        kc_refresh = AsyncMock(return_value={"access_token": "should-not", "refresh_token": "nope"})

        with (
            patch("app.api.auth.me.get_session", new=AsyncMock(return_value=fresh_session)),
            patch("app.api.auth.me.kc_service.refresh_tokens", new=kc_refresh),
            patch("app.api.auth.me.save_session", new=AsyncMock()) as save_mock,
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "sid"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        kc_refresh.assert_not_called()
        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_kc_error_but_session_already_refreshed_returns_ok(
        self, authed_client_factory, app
    ):
        """Гонка ротации: наш refresh упал (invalid_grant), но соседний поток уже
        обновил access_token в сессии — пользователя не выбиваем, возвращаем ok."""
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        # 1-й get_session — стартовое состояние (без refreshed_at → без коалесинга);
        # 2-й (latest, в ветке except) — access_token уже обновлён соседом.
        get_session_mock = AsyncMock(
            side_effect=[
                {"refresh_token": "old-rt", "access_token": "old-at"},
                {"refresh_token": "new-rt", "access_token": "new-at"},
            ]
        )

        with (
            patch("app.api.auth.me.get_session", new=get_session_mock),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(side_effect=Exception("invalid_grant")),
            ),
            patch("app.api.auth.me.save_session", new=AsyncMock()) as save_mock,
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "sid"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert get_session_mock.await_count == 2
        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_kc_400_deletes_session(self, authed_client_factory, app):
        """HTTP 400 от Keycloak — мёртвый refresh token → сессия удаляется из Redis.

        Диагностика тела ответа Keycloak ({"error":"invalid_grant",...}) покрыта
        отдельным unit-тестом ``test_extract_kc_error_context_*`` — HTTP-путь
        здесь перекрыт FastAPILimiter-init ошибкой окружения для проверки лога.
        """
        import httpx
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        kc_error = httpx.HTTPStatusError(
            "400 Bad Request", request=MagicMock(), response=mock_response
        )

        delete_mock = AsyncMock()
        with (
            patch(
                "app.api.auth.me.get_session",
                new=AsyncMock(return_value={"refresh_token": "dead-rt", "access_token": "old-at"}),
            ),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(side_effect=kc_error),
            ),
            patch("app.api.auth.me.delete_session", new=delete_mock),
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "dead-session-id"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401
        delete_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kc_non_400_error_does_not_delete_session(self, authed_client_factory, app):
        """Транзиентная ошибка Keycloak (не 400) — сессия НЕ удаляется.

        Тело ответа логируется для диагностики (см. ``_extract_kc_error_context``).
        """
        import httpx
        from httpx import ASGITransport, AsyncClient

        _ac, _user = authed_client_factory(role="reader", deleted_at=None)
        from app.core.security import SESSION_COOKIE_NAME

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 503
        kc_error = httpx.HTTPStatusError(
            "503 Service Unavailable", request=MagicMock(), response=mock_response
        )

        delete_mock = AsyncMock()
        with (
            patch(
                "app.api.auth.me.get_session",
                new=AsyncMock(return_value={"refresh_token": "rt", "access_token": "at"}),
            ),
            patch(
                "app.api.auth.me.kc_service.refresh_tokens",
                new=AsyncMock(side_effect=kc_error),
            ),
            patch("app.api.auth.me.delete_session", new=delete_mock),
        ):
            from tests.conftest import _CSRF_TOKEN

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "session-id"},
            ) as client2:
                resp = await client2.post("/api/v1/auth/refresh")

        assert resp.status_code == 401
        delete_mock.assert_not_awaited()


# ── get_user_for_refresh (облегчённая session-auth для /auth/refresh) ──────────
# Ключевое отличие от get_current_user: НЕ валидирует exp access-токена, чтобы
# фоновая вкладка с истёкшим токеном могла тихо обновиться (см. docs/wip/auth.md).


def _db_returning(user: object) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=user)
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetUserForRefresh:
    @pytest.mark.asyncio
    async def test_no_session_cookie_returns_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_user_for_refresh

        with pytest.raises(HTTPException) as exc:
            await get_user_for_refresh(
                request=MagicMock(), redis=MagicMock(), db=MagicMock(), session_id=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_session_in_redis_returns_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_user_for_refresh

        with (
            patch("app.api.deps.get_session", new=AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_user_for_refresh(
                request=MagicMock(), redis=MagicMock(), db=MagicMock(), session_id="sid"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_user_id_in_session_returns_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_user_for_refresh

        with (
            patch(
                "app.api.deps.get_session",
                new=AsyncMock(return_value={"auth_source": "keycloak"}),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await get_user_for_refresh(
                request=MagicMock(), redis=MagicMock(), db=MagicMock(), session_id="sid"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_user_for_refresh

        with (
            patch(
                "app.api.deps.get_session",
                new=AsyncMock(return_value={"user_id": "not-a-uuid"}),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await get_user_for_refresh(
                request=MagicMock(), redis=MagicMock(), db=MagicMock(), session_id="sid"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_returns_401(self):
        from fastapi import HTTPException

        from app.api.deps import get_user_for_refresh

        session = {"user_id": str(uuid.uuid4()), "auth_source": "keycloak"}
        with (
            patch("app.api.deps.get_session", new=AsyncMock(return_value=session)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_user_for_refresh(
                request=MagicMock(),
                redis=MagicMock(),
                db=_db_returning(None),
                session_id="sid",
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_access_token_still_resolves_user(self):
        """Главное свойство фикса: access_token НЕ парсится → истёкший токен не
        мешает refresh. Пользователь берётся из сессии по user_id."""
        from app.api.deps import get_user_for_refresh

        user = SimpleNamespace(id=uuid.uuid4(), role="reader")
        session = {
            "user_id": str(user.id),
            "auth_source": "keycloak",
            "access_token": "expired.garbage.jwt",
        }
        with (
            patch("app.api.deps.get_session", new=AsyncMock(return_value=session)),
            patch("app.api.deps.parse_jwt_claims") as mock_parse,
            patch("app.api.deps.bind_request_context"),
        ):
            result = await get_user_for_refresh(
                request=MagicMock(),
                redis=MagicMock(),
                db=_db_returning(user),
                session_id="sid",
            )
        assert result is user
        mock_parse.assert_not_called()


class TestAuthLogin:
    @pytest.mark.asyncio
    async def test_login_redirects_to_keycloak(self, app):
        from httpx import ASGITransport, AsyncClient

        from app.services.keycloak.settings import _KCSettings
        from tests.conftest import _CSRF_TOKEN

        kcs = _KCSettings(
            keycloak_url="https://kc.example.com",
            keycloak_realm="portal",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )

        with (
            patch("app.api.auth.oidc.save_pkce_state", new=AsyncMock()),
            patch(
                "app.api.auth.oidc.kc_service._get_kc_settings_async",
                new=AsyncMock(return_value=kcs),
            ),
            patch(
                "app.api.auth.oidc.kc_service.get_authorization_url",
                return_value="https://kc.example.com/auth?code=abc",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/login")

        assert resp.status_code == 302
        assert "kc.example.com" in resp.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_login_sets_loop_guard_cookie(self, app):
        """A4: успешный редирект на Keycloak проставляет server-side счётчик попыток."""
        from httpx import ASGITransport, AsyncClient

        from app.services.keycloak.settings import _KCSettings
        from tests.conftest import _CSRF_TOKEN

        kcs = _KCSettings(
            keycloak_url="https://kc.example.com",
            keycloak_realm="portal",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        with (
            patch("app.api.auth.oidc.save_pkce_state", new=AsyncMock()),
            patch(
                "app.api.auth.oidc.kc_service._get_kc_settings_async",
                new=AsyncMock(return_value=kcs),
            ),
            patch(
                "app.api.auth.oidc.kc_service.get_authorization_url",
                return_value="https://kc.example.com/auth?code=abc",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/login")

        assert resp.status_code == 302
        assert "sso_attempts" in resp.headers.get("set-cookie", "")

    @pytest.mark.asyncio
    async def test_login_blocks_when_loop_limit_reached(self, app):
        """A4: при ≥ SSO_LOOP_LIMIT недавних попыток в cookie — 302 на loop_detected, без обращения к Keycloak."""
        import json
        import time

        from httpx import ASGITransport, AsyncClient

        from app.api.auth._helpers import SSO_LOOP_LIMIT
        from app.services.keycloak.settings import _KCSettings
        from tests.conftest import _CSRF_TOKEN

        kcs = _KCSettings(
            keycloak_url="https://kc.example.com",
            keycloak_realm="portal",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        now = time.time()
        attempts_cookie = json.dumps([round(now, 3)] * SSO_LOOP_LIMIT)
        get_url_mock = MagicMock(return_value="https://kc.example.com/auth?code=abc")
        with (
            patch("app.api.auth.oidc.save_pkce_state", new=AsyncMock()),
            patch(
                "app.api.auth.oidc.kc_service._get_kc_settings_async",
                new=AsyncMock(return_value=kcs),
            ),
            patch("app.api.auth.oidc.kc_service.get_authorization_url", new=get_url_mock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, "sso_attempts": attempts_cookie},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/login")

        assert resp.status_code == 302
        assert resp.headers.get("location") == "/auth/error?reason=loop_detected"
        get_url_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_ignores_stale_attempts(self, app):
        """A4: протухшие (> окна) попытки не считаются — логин проходит нормально."""
        import json

        from httpx import ASGITransport, AsyncClient

        from app.api.auth._helpers import SSO_LOOP_LIMIT, SSO_LOOP_WINDOW_S
        from app.services.keycloak.settings import _KCSettings
        from tests.conftest import _CSRF_TOKEN

        kcs = _KCSettings(
            keycloak_url="https://kc.example.com",
            keycloak_realm="portal",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        stale = 1000.0
        attempts_cookie = json.dumps([round(stale, 3)] * (SSO_LOOP_LIMIT + 2))
        with (
            patch("app.api.auth.oidc.save_pkce_state", new=AsyncMock()),
            patch(
                "app.api.auth.oidc.kc_service._get_kc_settings_async",
                new=AsyncMock(return_value=kcs),
            ),
            patch(
                "app.api.auth.oidc.kc_service.get_authorization_url",
                return_value="https://kc.example.com/auth?code=abc",
            ),
        ):
            assert SSO_LOOP_WINDOW_S < 100_000  # sanity: stale=1000 далеко в прошлом
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, "sso_attempts": attempts_cookie},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/login")

        assert resp.status_code == 302
        assert "kc.example.com" in resp.headers.get("location", "")


class TestLogoutGet:
    @pytest.mark.asyncio
    async def test_logout_get_with_session(self, app):
        from httpx import ASGITransport, AsyncClient

        from app.core.security import SESSION_COOKIE_NAME
        from tests.conftest import _CSRF_TOKEN

        with patch("app.api.auth.logout.delete_session", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "test-session"},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/logout")

        assert resp.status_code == 302

    @pytest.mark.asyncio
    async def test_logout_get_without_session(self, app):
        from httpx import ASGITransport, AsyncClient

        from tests.conftest import _CSRF_TOKEN

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
            follow_redirects=False,
        ) as client:
            resp = await client.get("/api/v1/auth/logout")

        assert resp.status_code == 302

    @pytest.mark.asyncio
    async def test_logout_get_cross_site_rejected(self, app):
        """A3: forced-logout via cross-site sub-resource (<img>) → 403, session kept."""
        from httpx import ASGITransport, AsyncClient

        from app.core.security import SESSION_COOKIE_NAME
        from tests.conftest import _CSRF_TOKEN

        delete_mock = AsyncMock()
        with patch("app.api.auth.logout.delete_session", new=delete_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Origin": "http://test",
                    "x-xsrf-token": _CSRF_TOKEN,
                    "Sec-Fetch-Site": "cross-site",
                },
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "victim-session"},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/logout")

        assert resp.status_code == 403
        delete_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logout_get_same_origin_navigation_allowed(self, app):
        """A3: genuine same-origin navigation still logs out (session destroyed)."""
        from httpx import ASGITransport, AsyncClient

        from app.core.security import SESSION_COOKIE_NAME
        from tests.conftest import _CSRF_TOKEN

        delete_mock = AsyncMock()
        with patch("app.api.auth.logout.delete_session", new=delete_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "Origin": "http://test",
                    "x-xsrf-token": _CSRF_TOKEN,
                    "Sec-Fetch-Site": "same-origin",
                },
                cookies={"XSRF-TOKEN": _CSRF_TOKEN, SESSION_COOKIE_NAME: "my-session"},
                follow_redirects=False,
            ) as client:
                resp = await client.get("/api/v1/auth/logout")

        assert resp.status_code == 302
        delete_mock.assert_awaited_once()
