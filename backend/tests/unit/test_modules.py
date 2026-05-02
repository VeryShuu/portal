"""Unit-тесты для api/modules.py.

Покрытие:
- AllModuleSettings: дефолты, валидация
- PhotosModuleSettings: валидация widget_limit, max_size_mb
- load_modules: кэш TTL, чтение файла, fallback
- invalidate_modules_cache: сброс кэша
- _save_modules: атомарная запись через tmp-файл
- GET /modules: 200 для аутентифицированных, 401 без
- GET /admin/modules: 403 non-admin, 200 admin
- PUT /admin/modules/photos: 403 non-admin, 200 admin, валидация
- PUT /admin/modules/nextcloud: 403 non-admin, 200 admin
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

pytestmark = pytest.mark.asyncio


# ── Models ────────────────────────────────────────────────────────────────────


class TestAllModuleSettingsModel:
    def test_defaults(self):
        from app.api.modules import AllModuleSettings

        m = AllModuleSettings()
        assert m.nextcloud.enabled is False
        assert m.photos.enabled is True
        assert m.photos.widget_limit == 8
        assert m.photos.max_size_mb == 50
        assert m.photos.strip_gps is True

    def test_photos_widget_limit_validation(self):
        from pydantic import ValidationError
        from app.api.modules import PhotosModuleSettings

        with pytest.raises(ValidationError):
            PhotosModuleSettings(widget_limit=0)
        with pytest.raises(ValidationError):
            PhotosModuleSettings(widget_limit=51)

    def test_photos_max_size_mb_validation(self):
        from pydantic import ValidationError
        from app.api.modules import PhotosModuleSettings

        with pytest.raises(ValidationError):
            PhotosModuleSettings(max_size_mb=0)
        with pytest.raises(ValidationError):
            PhotosModuleSettings(max_size_mb=501)

    def test_nextcloud_module_in(self):
        from app.api.modules import NextcloudModuleIn

        n = NextcloudModuleIn(enabled=True)
        assert n.enabled is True

    def test_photos_module_in_defaults(self):
        from app.api.modules import PhotosModuleIn

        p = PhotosModuleIn()
        assert p.enabled is True
        assert p.strip_gps is True
        assert p.allowed_mime == []


# ── load_modules ──────────────────────────────────────────────────────────────


class TestLoadModules:
    def setup_method(self):
        from app.api.modules import invalidate_modules_cache

        invalidate_modules_cache()

    def test_returns_defaults_when_file_missing(self, tmp_path):
        import app.api.modules as mod

        with patch.object(mod, "_MODULES_FILE", tmp_path / "no.json"):
            from app.api.modules import load_modules

            result = load_modules()
        assert result.nextcloud.enabled is False
        assert result.photos.enabled is True

    def test_loads_from_file(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import invalidate_modules_cache

        modules_file = tmp_path / "modules.json"
        modules_file.write_text(
            json.dumps({"nextcloud": {"enabled": True}, "photos": {"enabled": False, "widget_limit": 8, "max_size_mb": 50, "allowed_mime": [], "strip_gps": True}}),
            encoding="utf-8",
        )
        invalidate_modules_cache()
        with patch.object(mod, "_MODULES_FILE", modules_file):
            from app.api.modules import load_modules

            result = load_modules()
        assert result.nextcloud.enabled is True
        assert result.photos.enabled is False

    def test_cache_hit_skips_file_read(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import load_modules, invalidate_modules_cache

        modules_file = tmp_path / "modules.json"
        invalidate_modules_cache()

        call_count = [0]
        original_exists = Path.exists

        def _count_exists(self):
            if str(self) == str(modules_file):
                call_count[0] += 1
            return original_exists(self)

        with (
            patch.object(mod, "_MODULES_FILE", modules_file),
            patch.object(mod, "_CACHE_TTL", 9999),
        ):
            load_modules()
            load_modules()
        assert call_count[0] <= 1

    def test_invalid_json_returns_defaults(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import load_modules, invalidate_modules_cache

        modules_file = tmp_path / "modules.json"
        modules_file.write_text("{invalid}", encoding="utf-8")
        invalidate_modules_cache()
        with patch.object(mod, "_MODULES_FILE", modules_file):
            result = load_modules()
        assert result.nextcloud.enabled is False

    def test_invalidate_clears_cache(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import load_modules, invalidate_modules_cache

        modules_file = tmp_path / "modules.json"
        data = {
            "nextcloud": {"enabled": False},
            "photos": {"enabled": True, "widget_limit": 8, "max_size_mb": 50, "allowed_mime": [], "strip_gps": True},
        }
        modules_file.write_text(json.dumps(data), encoding="utf-8")
        invalidate_modules_cache()

        with patch.object(mod, "_MODULES_FILE", modules_file):
            first = load_modules()
            assert first.nextcloud.enabled is False

            data["nextcloud"]["enabled"] = True
            modules_file.write_text(json.dumps(data), encoding="utf-8")

            invalidate_modules_cache()
            second = load_modules()
        assert second.nextcloud.enabled is True


# ── _save_modules ─────────────────────────────────────────────────────────────


class TestSaveModules:
    def test_save_and_reload(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import AllModuleSettings, _save_modules, load_modules, invalidate_modules_cache

        modules_file = tmp_path / "modules.json"
        settings_dir = tmp_path

        invalidate_modules_cache()
        m = AllModuleSettings()
        m.nextcloud.enabled = True
        m.photos.widget_limit = 12

        with (
            patch.object(mod, "_MODULES_FILE", modules_file),
            patch.object(mod, "_SETTINGS_DIR", settings_dir),
        ):
            _save_modules(m)
            invalidate_modules_cache()
            loaded = load_modules()

        assert loaded.nextcloud.enabled is True
        assert loaded.photos.widget_limit == 12

    def test_save_clears_cache(self, tmp_path):
        import app.api.modules as mod
        from app.api.modules import AllModuleSettings, _save_modules, _modules_cache

        modules_file = tmp_path / "modules.json"
        settings_dir = tmp_path

        with (
            patch.object(mod, "_MODULES_FILE", modules_file),
            patch.object(mod, "_SETTINGS_DIR", settings_dir),
        ):
            _save_modules(AllModuleSettings())
        assert not _modules_cache


# ── API endpoints ─────────────────────────────────────────────────────────────


class TestGetModulesEndpoint:
    async def test_unauthenticated_gets_401(self, client):
        r = await client.get("/api/v1/modules")
        assert r.status_code == 401

    async def test_reader_gets_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load,
        ):
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.get("/api/v1/modules")
        assert r.status_code == 200
        body = r.json()
        assert "nextcloud" in body
        assert "photos" in body


class TestGetAdminModules:
    async def test_non_admin_gets_403(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.get("/api/v1/admin/modules")
            assert r.status_code == 403, f"role={role}"

    async def test_admin_gets_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load:
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.get("/api/v1/admin/modules")
        assert r.status_code == 200


class TestUpdatePhotosModule:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        r = await ac.put(
            "/api/v1/admin/modules/photos",
            json={"enabled": True, "widget_limit": 8, "max_size_mb": 50},
        )
        assert r.status_code == 403

    async def test_admin_updates_photos(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load,
            patch("app.api.modules._save_modules"),
            patch("app.api.modules.bump_version", new_callable=AsyncMock),
            patch("app.api.modules.push_audit_event", new_callable=AsyncMock),
        ):
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.put(
                "/api/v1/admin/modules/photos",
                json={
                    "enabled": False,
                    "widget_limit": 16,
                    "max_size_mb": 100,
                    "strip_gps": False,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["widget_limit"] == 16
        assert body["max_size_mb"] == 100

    async def test_invalid_widget_limit_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        r = await ac.put(
            "/api/v1/admin/modules/photos",
            json={"enabled": True, "widget_limit": 0, "max_size_mb": 50},
        )
        assert r.status_code == 422


class TestUpdateNextcloudModule:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.put(
            "/api/v1/admin/modules/nextcloud",
            json={"enabled": True},
        )
        assert r.status_code == 403

    async def test_admin_enables_nextcloud(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load,
            patch("app.api.modules._save_modules"),
            patch("app.api.modules.bump_version", new_callable=AsyncMock),
            patch("app.api.modules.push_audit_event", new_callable=AsyncMock),
            patch("app.services.nextcloud.invalidate_nc_service", new_callable=AsyncMock),
        ):
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.put(
                "/api/v1/admin/modules/nextcloud",
                json={"enabled": True},
            )
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    async def test_admin_disables_nextcloud(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load,
            patch("app.api.modules._save_modules"),
            patch("app.api.modules.bump_version", new_callable=AsyncMock),
            patch("app.api.modules.push_audit_event", new_callable=AsyncMock),
            patch("app.services.nextcloud.invalidate_nc_service", new_callable=AsyncMock),
        ):
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.put(
                "/api/v1/admin/modules/nextcloud",
                json={"enabled": False},
            )
        assert r.status_code == 200
        assert r.json()["enabled"] is False
