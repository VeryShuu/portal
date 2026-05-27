"""Unit-тесты для app/api/users/routes_me.py.

Покрытие:
- GET /users/me — возвращает текущего пользователя
- PATCH /users/me/profile — вызывает users_me_service.patch_my_profile
- PATCH /users/me/preferences — вызывает users_me_service.patch_my_preferences
- POST /users/me/avatar — вызывает users_me_service.upload_avatar
- PATCH /users/me/password — вызывает users_me_service.change_my_password
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")


def _make_user(role: str = "reader", **kwargs) -> SimpleNamespace:
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=kwargs.get("id", uuid.uuid4()),
        role=role,
        email=kwargs.get("email", f"{role}@test.local"),
        full_name=kwargs.get("full_name", "Test User"),
        auth_source=kwargs.get("auth_source", "keycloak"),
        is_active=True,
        deleted_at=None,
        department=kwargs.get("department"),
        position=kwargs.get("position"),
        phone=None,
        avatar_url=None,
        attributes={},
        preferences={},
        presence_status=kwargs.get("presence_status", "office"),
        lang=kwargs.get("lang", "ru"),
        created_at=kwargs.get("created_at", datetime.now(UTC)),
        updated_at=kwargs.get("updated_at", datetime.now(UTC)),
        last_login_at=None,
        notify_email=kwargs.get("notify_email", True),
        notify_inapp=kwargs.get("notify_inapp", True),
        staff_sort_order=None,
        staff_hidden=False,
    )


class TestGetMe:
    @pytest.mark.asyncio
    async def test_returns_current_user(self, authed_client_factory):
        user_id = uuid.uuid4()
        ac, user = authed_client_factory(
            role="reader",
            id=user_id,
            email="user@test.local",
            full_name="Test Reader",
        )
        async with ac:
            resp = await ac.get("/api/v1/users/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user_id)
        assert data["role"] == "reader"

    @pytest.mark.asyncio
    async def test_returns_admin_role(self, authed_client_factory):
        ac, user = authed_client_factory(role="admin")
        async with ac:
            resp = await ac.get("/api/v1/users/me")

        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


class TestPatchMyProfile:
    @pytest.mark.asyncio
    async def test_updates_profile_and_returns_user(self, authed_client_factory):
        user_id = uuid.uuid4()
        ac, user = authed_client_factory(role="reader", id=user_id)

        updated_user = _make_user(role="reader", id=user_id, full_name="Updated Name")

        with patch(
            "app.api.users.routes_me.users_me_service.patch_my_profile",
            new=AsyncMock(return_value=updated_user),
        ):
            async with ac:
                resp = await ac.patch(
                    "/api/v1/users/me/profile",
                    json={"full_name": "Updated Name"},
                )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client):
        resp = await client.patch("/api/v1/users/me/profile", json={})
        assert resp.status_code in (401, 403)


class TestPatchMyPreferences:
    @pytest.mark.asyncio
    async def test_updates_preferences_and_returns_user(self, authed_client_factory):
        user_id = uuid.uuid4()
        ac, user = authed_client_factory(role="reader", id=user_id)

        updated_user = _make_user(role="reader", id=user_id)

        with patch(
            "app.api.users.routes_me.users_me_service.patch_my_preferences",
            new=AsyncMock(return_value=updated_user),
        ):
            async with ac:
                resp = await ac.patch(
                    "/api/v1/users/me/preferences",
                    json={"locale": "en"},
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client):
        resp = await client.patch("/api/v1/users/me/preferences", json={})
        assert resp.status_code in (401, 403)


class TestUploadAvatar:
    @pytest.mark.asyncio
    async def test_uploads_avatar_and_returns_user(self, authed_client_factory):
        user_id = uuid.uuid4()
        ac, user = authed_client_factory(role="reader", id=user_id)

        updated_user = _make_user(role="reader", id=user_id)

        with patch(
            "app.api.users.routes_me.users_me_service.upload_avatar",
            new=AsyncMock(return_value=updated_user),
        ):
            async with ac:
                resp = await ac.post(
                    "/api/v1/users/me/avatar",
                    files={"file": ("avatar.jpg", b"fake-image-data", "image/jpeg")},
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client):
        resp = await client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("avatar.jpg", b"data", "image/jpeg")},
        )
        assert resp.status_code in (401, 403)


class TestChangeMyPassword:
    @pytest.mark.asyncio
    async def test_changes_password_successfully(self, authed_client_factory):
        ac, user = authed_client_factory(role="reader", auth_source="local")

        with patch(
            "app.api.users.routes_me.users_me_service.change_my_password",
            new=AsyncMock(return_value={"ok": True}),
        ):
            async with ac:
                resp = await ac.patch(
                    "/api/v1/users/me/password",
                    json={"current_password": "oldpass", "new_password": "NewPass123!"},
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client):
        resp = await client.patch(
            "/api/v1/users/me/password",
            json={"old_password": "old", "new_password": "new"},
        )
        assert resp.status_code in (401, 403)
