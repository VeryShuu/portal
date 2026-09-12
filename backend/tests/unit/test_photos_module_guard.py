"""Test PhotosGuard: жёсткий kill-switch модуля (PA-008).

Решение владельца (2026-09-02): выключение Photos закрывает ВЕСЬ prefix
/photos — включая публичные share-ссылки, которые переживать выключение
не должны. Guard живёт на родительском роутере и выполняется до auth/ACL:
анонимный запрос к админ-роуту получает 404 (не 401), публичный токен — 404.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


def _modules(*, enabled: bool):
    from app.core.modules_config import AllModuleSettings, PhotosModuleSettings

    return AllModuleSettings(photos=PhotosModuleSettings(enabled=enabled))


def _patch_guard(*, enabled: bool):
    return patch(
        "app.api.photos.load_modules_shared",
        new_callable=AsyncMock,
        return_value=_modules(enabled=enabled),
    )


class TestPhotosModuleGuard:
    @pytest.mark.asyncio
    async def test_disabled_public_share_returns_404(self, client):
        """Выключение модуля убивает публичные share-ссылки (аноним, до ACL)."""
        with _patch_guard(enabled=False):
            r = await client.get("/api/v1/photos/public/some-token/info")
        assert r.status_code == 404
        assert "disabled" in r.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_disabled_admin_route_404_before_auth(self, client):
        """404 (не 401) на админ-роуте: guard срабатывает раньше auth-dependencies."""
        with _patch_guard(enabled=False):
            r = await client.get("/api/v1/photos/folders")
        assert r.status_code == 404
        assert "disabled" in r.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_enabled_does_not_block(self, client):
        """Включённый модуль: guard пропускает; аноним далее получает 401 от auth."""
        with _patch_guard(enabled=True):
            r = await client.get("/api/v1/photos/folders")
        assert r.status_code == 401
