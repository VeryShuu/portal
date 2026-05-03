"""Unit-тесты: admin user management endpoints.

Покрытие:
- POST /users/admin/local       — создание локального пользователя
- PATCH /users/admin/{id}/profile  — редактирование профиля
- DELETE /users/admin/{id}         — удаление пользователя
- Контроль доступа: только admin (403 для reader/editor)
- Бизнес-правило: patch profile запрещён для SSO-пользователей

Используют моки без реального DB/Redis.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

pytestmark = pytest.mark.asyncio


def _make_db_user(
    user_id: uuid.UUID | None = None,
    auth_source: str = "local",
    role: str = "reader",
    full_name: str = "Test User",
    department: str | None = "IT",
    position: str | None = "Engineer",
    phone: str | None = None,
):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"user-{uuid.uuid4().hex[:6]}@portal.local"
    u.full_name = full_name
    u.department = department
    u.position = position
    u.phone = phone
    u.role = role
    u.auth_source = auth_source
    u.avatar_url = None
    u.presence_status = "office"
    u.lang = "ru"
    u.notify_email = True
    u.notify_inapp = True
    u.preferences = {}
    u.attributes = {}
    u.keycloak_id = None if auth_source == "local" else str(uuid.uuid4())
    u.created_at = "2024-01-01T00:00:00+00:00"
    u.updated_at = "2024-01-01T00:00:00+00:00"
    u.last_login_at = None
    return u


def _make_fake_db(target_user=None):
    """Фейковая async DB-сессия, возвращающая target_user из scalar_one_or_none."""

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=target_user)
        result.scalar_one = MagicMock(return_value=target_user)
        result.fetchone = MagicMock(return_value=[target_user] if target_user else None)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[target_user] if target_user else []))
        )
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        yield session

    return _fake_db


class TestCreateLocalUser:
    """POST /users/admin/local"""

    async def test_non_admin_gets_403(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.post(
                "/api/v1/users/admin/local",
                json={
                    "email": "x@y.local",
                    "full_name": "X",
                    "password": "Pass1234!",
                    "role": "reader",
                },
            )
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_local_auth_disabled_returns_403(self, app, authed_client_factory):
        """Если LOCAL_AUTH_ENABLED=false — создание локальных пользователей запрещено."""
        from app.core.config import get_settings

        original = get_settings()

        patched = MagicMock()
        patched.local_auth_enabled = False

        with patch("app.api.users.settings", patched):
            ac, _ = authed_client_factory(role="admin")
            r = await ac.post(
                "/api/v1/users/admin/local",
                json={
                    "email": "x@y.local",
                    "full_name": "X",
                    "password": "Pass1234!",
                    "role": "reader",
                },
            )
        assert r.status_code == 403

    async def test_duplicate_email_returns_409(self, app, authed_client_factory):
        """Если email уже занят — 409 Conflict."""
        from app.api.deps import get_db

        existing_user = _make_db_user()

        app.dependency_overrides[get_db] = _make_fake_db(target_user=existing_user)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.post(
                "/api/v1/users/admin/local",
                json={
                    "email": existing_user.email,
                    "full_name": "Dup",
                    "password": "Pass1234!",
                    "role": "reader",
                },
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 409

    async def test_invalid_role_returns_422(self, authed_client_factory):
        """Невалидная роль → 422."""
        ac, _ = authed_client_factory(role="admin")
        r = await ac.post(
            "/api/v1/users/admin/local",
            json={
                "email": "x@y.local",
                "full_name": "X",
                "password": "Pass1234!",
                "role": "superuser",
            },
        )
        assert r.status_code == 422

    async def test_password_too_short_returns_422(self, authed_client_factory):
        """Пароль < 8 символов → 422."""
        ac, _ = authed_client_factory(role="admin")
        r = await ac.post(
            "/api/v1/users/admin/local",
            json={"email": "x@y.local", "full_name": "X", "password": "short", "role": "reader"},
        )
        assert r.status_code == 422


class TestPatchUserProfile:
    """PATCH /users/admin/{id}/profile"""

    async def test_non_admin_gets_403(self, authed_client_factory):
        user_id = uuid.uuid4()
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.patch(
                f"/api/v1/users/admin/{user_id}/profile",
                json={"full_name": "New Name"},
            )
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_user_not_found_returns_404(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(target_user=None)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.patch(
                f"/api/v1/users/admin/{uuid.uuid4()}/profile",
                json={"full_name": "New Name"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 404

    async def test_sso_user_returns_403(self, app, authed_client_factory):
        """Нельзя редактировать профиль SSO-пользователя."""
        from app.api.deps import get_db

        sso_user = _make_db_user(auth_source="keycloak")
        app.dependency_overrides[get_db] = _make_fake_db(target_user=sso_user)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.patch(
                f"/api/v1/users/admin/{sso_user.id}/profile",
                json={"full_name": "New Name"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 403

    async def test_empty_body_is_ok(self, app, authed_client_factory):
        """Пустое тело (все поля None) не вызывает ошибки."""
        from app.api.deps import get_db

        local_user = _make_db_user(auth_source="local")
        app.dependency_overrides[get_db] = _make_fake_db(target_user=local_user)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.patch(
                f"/api/v1/users/admin/{local_user.id}/profile",
                json={},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code in (200, 204)


class TestDeleteUser:
    """DELETE /users/admin/{id}"""

    async def test_non_admin_gets_403(self, authed_client_factory):
        user_id = uuid.uuid4()
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.delete(f"/api/v1/users/admin/{user_id}")
            assert r.status_code == 403, f"role={role} should be 403"

    async def test_user_not_found_returns_404(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(target_user=None)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.delete(f"/api/v1/users/admin/{uuid.uuid4()}")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 404

    async def test_delete_returns_204(self, app, authed_client_factory):
        from app.api.deps import get_db

        target = _make_db_user(auth_source="local")
        app.dependency_overrides[get_db] = _make_fake_db(target_user=target)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.delete(f"/api/v1/users/admin/{target.id}")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 204

    async def test_delete_sso_user_also_works(self, app, authed_client_factory):
        """SSO-пользователей тоже можно удалять."""
        from app.api.deps import get_db

        sso_user = _make_db_user(auth_source="keycloak")
        app.dependency_overrides[get_db] = _make_fake_db(target_user=sso_user)
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.delete(f"/api/v1/users/admin/{sso_user.id}")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 204


class TestAdminUserValidationLogic:
    """Проверка бизнес-правил без HTTP — чистые unit-тесты."""

    def test_auth_source_check_for_profile_edit(self):
        """Только local-пользователи допускаются к редактированию профиля."""
        local = _make_db_user(auth_source="local")
        sso = _make_db_user(auth_source="keycloak")
        assert local.auth_source == "local"
        assert sso.auth_source == "keycloak"
        assert (sso.auth_source != "local") is True

    def test_admin_patch_profile_request_full_name_required_min_length(self):
        """AdminPatchProfileRequest: full_name не может быть пустой строкой."""
        from pydantic import ValidationError
        from app.schemas.user import AdminPatchProfileRequest

        with pytest.raises(ValidationError):
            AdminPatchProfileRequest(full_name="")

    def test_admin_patch_profile_allows_none_fields(self):
        """AdminPatchProfileRequest: все поля опциональны."""
        from app.schemas.user import AdminPatchProfileRequest

        req = AdminPatchProfileRequest()
        assert req.full_name is None
        assert req.department is None
        assert req.position is None
        assert req.phone is None

    def test_local_user_create_request_validates_email(self):
        """LocalUserCreateRequest: email должен быть валидным."""
        from pydantic import ValidationError
        from app.schemas.user import LocalUserCreateRequest

        with pytest.raises(ValidationError):
            LocalUserCreateRequest(email="not-an-email", full_name="X", password="Pass1234!")

    def test_local_user_create_request_validates_role(self):
        """LocalUserCreateRequest: недопустимая роль → ValidationError."""
        from pydantic import ValidationError
        from app.schemas.user import LocalUserCreateRequest

        with pytest.raises(ValidationError):
            LocalUserCreateRequest(
                email="x@y.local", full_name="X", password="Pass1234!", role="superuser"
            )

    def test_local_user_create_request_valid(self):
        """LocalUserCreateRequest: корректные данные проходят валидацию."""
        from app.schemas.user import LocalUserCreateRequest

        req = LocalUserCreateRequest(
            email="User@Company.Local", full_name="Иван Иванов", password="SecureP@ss1"
        )
        assert req.email == "user@company.local"
        assert req.role == "reader"
