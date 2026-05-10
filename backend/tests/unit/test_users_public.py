"""
Тесты публичных endpoints справочника сотрудников.

Покрытие:
- GET /users            — список сотрудников (только авторизованные)
- GET /users/{user_id}  — профиль сотрудника по ID (только авторизованные)
- Контроль доступа: неавторизованный запрос → 401
- Бизнес-правило: несуществующий пользователь → 404
- Ответ содержит поля phone, position, department

Используют моки без реального DB/Redis.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")



def _make_db_user(
    user_id: uuid.UUID | None = None,
    full_name: str = "Иванов Иван",
    position: str | None = "Инженер",
    phone: str | None = "+7 999 123 45 67",
    department: str | None = "Разработка",
    role: str = "reader",
):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"user-{uuid.uuid4().hex[:6]}@portal.local"
    u.full_name = full_name
    u.department = department
    u.position = position
    u.phone = phone
    u.role = role
    u.auth_source = "local"
    u.avatar_url = None
    u.presence_status = "office"
    u.lang = "ru"
    u.notify_email = True
    u.notify_inapp = True
    u.preferences = {}
    u.attributes = {}
    u.keycloak_id = None
    u.created_at = "2024-01-01T00:00:00+00:00"
    u.updated_at = "2024-01-01T00:00:00+00:00"
    u.last_login_at = None
    return u


def _make_fake_db(target_user=None, user_list: list | None = None):
    """Фейковая async DB-сессия."""

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=target_user)
        result.scalar_one = MagicMock(return_value=len(user_list) if user_list is not None else 0)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=user_list or []))
        )
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    return _fake_db


class TestGetUserById:
    """GET /users/{user_id} — профиль сотрудника"""

    async def test_unauthenticated_returns_401(self, client):
        user_id = uuid.uuid4()
        r = await client.get(f"/api/v1/users/{user_id}")
        assert r.status_code == 401

    async def test_user_not_found_returns_404(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(target_user=None)
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get(f"/api/v1/users/{uuid.uuid4()}")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 404

    async def test_returns_200_with_phone_and_position(self, app, authed_client_factory):
        from app.api.deps import get_db

        user_id = uuid.uuid4()
        target = _make_db_user(
            user_id=user_id,
            full_name="Петров Пётр",
            position="Senior Developer",
            phone="+7 999 000 00 00",
            department="Backend",
        )
        app.dependency_overrides[get_db] = _make_fake_db(target_user=target)
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get(f"/api/v1/users/{user_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(user_id)
        assert data["full_name"] == "Петров Пётр"
        assert data["position"] == "Senior Developer"
        assert data["phone"] == "+7 999 000 00 00"
        assert data["department"] == "Backend"

    async def test_returns_200_when_phone_and_position_are_null(self, app, authed_client_factory):
        from app.api.deps import get_db

        user_id = uuid.uuid4()
        target = _make_db_user(user_id=user_id, position=None, phone=None)
        app.dependency_overrides[get_db] = _make_fake_db(target_user=target)
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get(f"/api/v1/users/{user_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        data = r.json()
        assert data["phone"] is None
        assert data["position"] is None

    async def test_any_role_can_view_profile(self, app, authed_client_factory):
        from app.api.deps import get_db

        user_id = uuid.uuid4()
        target = _make_db_user(user_id=user_id)
        for role in ("reader", "editor", "admin"):
            app.dependency_overrides[get_db] = _make_fake_db(target_user=target)
            ac, _ = authed_client_factory(role=role)
            try:
                r = await ac.get(f"/api/v1/users/{user_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)
            assert r.status_code == 200, f"role={role} должен видеть профиль"


class TestListUsers:
    """GET /users — список сотрудников"""

    async def test_unauthenticated_returns_401(self, client):
        r = await client.get("/api/v1/users")
        assert r.status_code == 401

    async def test_returns_200_with_items_and_total(self, app, authed_client_factory):
        from app.api.deps import get_db

        users = [_make_db_user(full_name=f"User {i}") for i in range(3)]
        app.dependency_overrides[get_db] = _make_fake_db(user_list=users)
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    async def test_reader_can_list_users(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(user_list=[])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200
