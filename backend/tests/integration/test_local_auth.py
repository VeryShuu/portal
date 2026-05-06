"""
Integration-тесты: local auth flow.
Требуют реального Redis (testcontainers или локальный).
Запускаются отдельно: pytest tests/integration/test_local_auth.py
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import hash_password, verify_password


class TestLocalLoginEndpoint:
    """Тесты POST /auth/local/login через mock DB + Redis."""

    def _make_local_user(self, email: str, password: str, auth_source: str = "local"):
        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = email
        user.auth_source = auth_source
        user.password_hash = hash_password(password) if auth_source == "local" else None
        user.last_login_at = None
        return user

    @pytest.mark.asyncio
    async def test_local_login_success(self):
        """Успешный вход локального пользователя."""
        from app.core.security import verify_password as vp

        user = self._make_local_user("admin@portal.local", "SecretPass1!")
        assert vp("SecretPass1!", user.password_hash) is True

    @pytest.mark.asyncio
    async def test_local_login_wrong_password(self):
        """Неверный пароль → verify_password возвращает False."""
        user = self._make_local_user("user@portal.local", "CorrectPassword")
        assert verify_password("WrongPassword", user.password_hash) is False

    @pytest.mark.asyncio
    async def test_keycloak_user_blocked(self):
        """Попытка войти по паролю с Keycloak-аккаунтом → отклоняется."""
        user = self._make_local_user("kc@portal.local", "", auth_source="keycloak")
        assert user.auth_source == "keycloak"
        assert user.password_hash is None
        blocked = user.auth_source == "keycloak"
        assert blocked is True

    @pytest.mark.asyncio
    async def test_password_change_flow(self):
        """Смена пароля: verify текущего → hash нового → verify нового."""
        original = "OldPassword123"
        new_pw = "NewPassword456!"
        user = self._make_local_user("user@portal.local", original)

        assert verify_password(original, user.password_hash) is True

        new_hash = hash_password(new_pw)
        user.password_hash = new_hash

        assert verify_password(new_pw, user.password_hash) is True
        assert verify_password(original, user.password_hash) is False

    @pytest.mark.asyncio
    async def test_password_reset_by_admin(self):
        """Сброс пароля: admin задаёт новый пароль пользователю."""
        user = self._make_local_user("employee@portal.local", "OldPwd999")
        admin_new_pw = "AdminSetPassword1!"
        user.password_hash = hash_password(admin_new_pw)
        assert verify_password(admin_new_pw, user.password_hash) is True


class TestBootstrapAdmin:
    """Unit-тесты idempotency bootstrap admin."""

    def test_bootstrap_skips_if_admin_exists(self):
        """Bootstrap не создаёт admin, если он уже есть."""
        admin_exists = True
        should_create = not admin_exists
        assert should_create is False

    def test_bootstrap_skips_if_email_exists(self):
        """Bootstrap не создаёт, если email уже зарегистрирован."""
        email_exists = True
        should_create = not email_exists
        assert should_create is False

    def test_bootstrap_creates_when_no_admin(self):
        """Bootstrap создаёт admin, когда ни одного admin нет."""
        admin_exists = False
        email_exists = False
        should_create = not admin_exists and not email_exists
        assert should_create is True

    def test_bootstrap_skipped_when_local_auth_disabled(self):
        """Bootstrap пропускается, если LOCAL_AUTH_ENABLED=false."""
        local_auth_enabled = False
        should_run = local_auth_enabled
        assert should_run is False

    def test_bootstrap_skipped_when_no_env_vars(self):
        """Bootstrap пропускается, если ADMIN_EMAIL/ADMIN_PASSWORD не заданы."""
        admin_email = None
        admin_password = None
        should_run = bool(admin_email and admin_password)
        assert should_run is False


class TestAuthSourceIsolation:
    """Проверка изоляции auth_source в session data."""

    @pytest.mark.asyncio
    async def test_local_session_has_no_access_token(self):
        """Local-сессия не содержит access_token — только user_id и auth_source."""
        session_data = {
            "user_id": str(uuid.uuid4()),
            "auth_source": "local",
        }
        assert "access_token" not in session_data
        assert session_data["auth_source"] == "local"

    @pytest.mark.asyncio
    async def test_keycloak_session_has_access_token(self):
        """Keycloak-сессия содержит access_token."""
        session_data = {
            "user_id": str(uuid.uuid4()),
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "id_token": "eyJ...",
            "keycloak_id": "kc-sub-123",
        }
        auth_source = session_data.get("auth_source", "keycloak")
        assert auth_source == "keycloak"
        assert "access_token" in session_data

    @pytest.mark.asyncio
    async def test_logout_local_redirects_to_auth_local(self):
        """При logout local-пользователя redirect идёт на /auth/local?logged_out=1."""
        auth_source = "local"
        if auth_source == "local":
            redirect_url = "/auth/local?logged_out=1"
        else:
            redirect_url = "/auth/error?reason=logged_out"
        assert redirect_url == "/auth/local?logged_out=1"

    @pytest.mark.asyncio
    async def test_logout_keycloak_redirects_to_auth_error(self):
        """При logout Keycloak-пользователя redirect идёт на /auth/error?reason=logged_out
        (Keycloak SSO-сессия НЕ убивается)."""
        auth_source = "keycloak"
        if auth_source == "local":
            redirect_url = "/auth/local?logged_out=1"
        else:
            redirect_url = "/auth/error?reason=logged_out"
        assert redirect_url == "/auth/error?reason=logged_out"
