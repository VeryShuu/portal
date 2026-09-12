"""Unit-тесты для admin-управления флагами уведомлений пользователя.

``users_admin_service.admin_get_notification_preferences`` /
``admin_patch_notification_preferences`` (+ self-ключ
``chat_notifications_enabled`` в ``patch_my_preferences``).

Паттерн — как ``TestPatchMyPreferencesService``: прямые вызовы сервиса с
моками db/repo.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.users import users_admin_service
from app.schemas.user import AdminPatchPreferencesRequest, PatchPreferencesRequest


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email="admin@mage.ru", role="admin")


def _target(prefs: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="user@mage.ru",
        role="reader",
        preferences=prefs if prefs is not None else {},
    )


def _db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())


def _patch_fetch(monkeypatch, target) -> AsyncMock:
    fetch = AsyncMock(return_value=target)
    monkeypatch.setattr("app.api.users.users_admin_service.users_repo.fetch_active_user", fetch)
    return fetch


@pytest.mark.asyncio
class TestAdminGetNotificationPreferences:
    async def test_returns_false_by_default(self, monkeypatch):
        target = _target()
        _patch_fetch(monkeypatch, target)
        result = await users_admin_service.admin_get_notification_preferences(_db(), target.id)
        assert result == {"chat_notifications_enabled": False}

    async def test_returns_saved_flag(self, monkeypatch):
        target = _target({"chat_notifications_enabled": True})
        _patch_fetch(monkeypatch, target)
        result = await users_admin_service.admin_get_notification_preferences(_db(), target.id)
        assert result == {"chat_notifications_enabled": True}

    async def test_missing_user_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.users.users_admin_service.users_repo.fetch_active_user",
            AsyncMock(return_value=None),
        )
        with pytest.raises(HTTPException) as ei:
            await users_admin_service.admin_get_notification_preferences(_db(), uuid.uuid4())
        assert ei.value.status_code == 404


@pytest.mark.asyncio
class TestAdminPatchNotificationPreferences:
    async def test_sets_flag_and_audits(self, monkeypatch):
        target = _target({"onboarding_completed": True})
        _patch_fetch(monkeypatch, target)
        db = _db()
        # refresh имитирует перезагрузку из БД — сервис читает итоговое
        # состояние preferences после commit.
        db.refresh = AsyncMock(
            side_effect=lambda t: setattr(
                t, "preferences", {"onboarding_completed": True, "chat_notifications_enabled": True}
            )
        )

        with (
            patch(
                "app.api.users.users_admin_service.users_repo.update_user_fields",
                new=AsyncMock(),
            ) as repo_update,
            patch.object(users_admin_service, "_emit_audit", new=AsyncMock()) as audit,
        ):
            result = await users_admin_service.admin_patch_preferences(
                db,
                object(),
                _admin(),
                target.id,
                AdminPatchPreferencesRequest(chat_notifications_enabled=True),
            )

        saved = repo_update.call_args[0][2]
        # Merge: служебные preferences не затёрты.
        assert saved["preferences"]["chat_notifications_enabled"] is True
        assert saved["preferences"]["onboarding_completed"] is True
        assert result == {"chat_notifications_enabled": True}
        db.commit.assert_awaited_once()
        audit.assert_awaited_once()

    async def test_noop_patch_returns_current_state(self, monkeypatch):
        """Пустой PATCH (None) — ничего не пишет, возвращает текущее состояние."""
        target = _target({"chat_notifications_enabled": True})
        _patch_fetch(monkeypatch, target)
        db = _db()

        with patch(
            "app.api.users.users_admin_service.users_repo.update_user_fields",
            new=AsyncMock(),
        ) as repo_update:
            result = await users_admin_service.admin_patch_preferences(
                db,
                object(),
                _admin(),
                target.id,
                AdminPatchPreferencesRequest(),
            )

        repo_update.assert_not_called()
        db.commit.assert_not_called()
        assert result == {"chat_notifications_enabled": True}

    async def test_missing_user_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.api.users.users_admin_service.users_repo.fetch_active_user",
            AsyncMock(return_value=None),
        )
        with pytest.raises(HTTPException) as ei:
            await users_admin_service.admin_patch_preferences(
                _db(),
                object(),
                _admin(),
                uuid.uuid4(),
                AdminPatchPreferencesRequest(chat_notifications_enabled=True),
            )
        assert ei.value.status_code == 404


@pytest.mark.asyncio
class TestPatchMyPreferencesChatFlag:
    """Self-ключ chat_notifications_enabled в users_me_service."""

    async def test_persists_flag(self):
        from app.api.users.users_me_service import patch_my_preferences

        user = SimpleNamespace(id=uuid.uuid4(), preferences={"hidden_link_ids": ["x"]})
        db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

        with patch(
            "app.api.users.users_me_service.users_repo.update_user_fields",
            new=AsyncMock(),
        ) as repo_update:
            await patch_my_preferences(
                db,
                user,
                PatchPreferencesRequest(chat_notifications_enabled=True),
            )

        saved = repo_update.call_args[0][2]["preferences"]
        assert saved["chat_notifications_enabled"] is True
        # Прочие ключи не затёрты.
        assert saved["hidden_link_ids"] == ["x"]
