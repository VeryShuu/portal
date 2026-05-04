import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def tmp_settings_dir(tmp_path: Path, monkeypatch):
    settings_dir = tmp_path / "settings"
    nginx_conf_dir = tmp_path / "nginx-conf"
    nginx_reload_dir = tmp_path / "nginx"
    certs_dir = tmp_path / "certs"
    settings_dir.mkdir()
    nginx_conf_dir.mkdir()
    nginx_reload_dir.mkdir()
    certs_dir.mkdir()

    import app.core.system_config as sc

    monkeypatch.setattr(sc, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(sc, "_SYSTEM_SETTINGS_FILE", settings_dir / "system.json")
    monkeypatch.setattr(sc, "_NGINX_CONF_DIR", nginx_conf_dir)
    monkeypatch.setattr(sc, "_NGINX_RELOAD_DIR", nginx_reload_dir)
    monkeypatch.setattr(sc, "_NGINX_RELOAD_TRIGGER", nginx_reload_dir / "reload-trigger")
    monkeypatch.setattr(sc, "_CERTS_DIR", certs_dir)
    monkeypatch.setattr(sc, "_settings_cache", {})

    return {
        "settings_dir": settings_dir,
        "nginx_conf_dir": nginx_conf_dir,
        "nginx_reload_dir": nginx_reload_dir,
        "certs_dir": certs_dir,
        "settings_file": settings_dir / "system.json",
        "reload_trigger": nginx_reload_dir / "reload-trigger",
    }


class TestLoadSystemSettings:
    def test_returns_defaults_when_file_missing(self, tmp_settings_dir, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h/db")
        monkeypatch.setenv("REDIS_URL", "redis://h")
        monkeypatch.setenv("SECRET_KEY", "exactly_thirty_two_characters_ok!")

        from app.core.system_config import load_system_settings

        s = load_system_settings()
        assert s.max_upload_size_mb == 100
        assert s.allowed_cidr == "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
        assert s.prometheus_metrics_enabled is True

    def test_loads_from_file(self, tmp_settings_dir):
        data = {
            "portal_base_url": "https://my.portal.local",
            "nextcloud_url": "https://nc.local",
            "nc_user_id_field": "sub",
            "nc_service_app_password": "secret123",
            "max_upload_size_mb": 200,
            "allowed_cidr": "192.168.1.0/24",
            "prometheus_metrics_enabled": False,
        }
        tmp_settings_dir["settings_file"].write_text(json.dumps(data), encoding="utf-8")

        from app.core.system_config import load_system_settings

        s = load_system_settings()
        assert s.portal_base_url == "https://my.portal.local"
        assert s.nc_user_id_field == "sub"
        assert s.max_upload_size_mb == 200
        assert s.allowed_cidr == "192.168.1.0/24"
        assert s.prometheus_metrics_enabled is False

    def test_cache_ttl(self, tmp_settings_dir):
        import app.core.system_config as sc
        from app.core.system_config import load_system_settings, SystemSettings

        cached = SystemSettings(portal_base_url="https://cached.local")
        sc._settings_cache["data"] = cached
        sc._settings_cache["fetched_at"] = time.monotonic()

        s = load_system_settings()
        assert s.portal_base_url == "https://cached.local"

    def test_cache_expires(self, tmp_settings_dir):
        import app.core.system_config as sc
        from app.core.system_config import load_system_settings, SystemSettings

        cached = SystemSettings(portal_base_url="https://old.local")
        sc._settings_cache["data"] = cached
        sc._settings_cache["fetched_at"] = time.monotonic() - 999

        data = {
            "portal_base_url": "https://fresh.local",
            "nextcloud_url": "",
            "nc_user_id_field": "preferred_username",
            "nc_service_app_password": "",
            "max_upload_size_mb": 100,
            "allowed_cidr": "10.0.0.0/8",
            "prometheus_metrics_enabled": True,
        }
        tmp_settings_dir["settings_file"].write_text(json.dumps(data), encoding="utf-8")

        s = load_system_settings()
        assert s.portal_base_url == "https://fresh.local"


class TestSaveAndToOut:
    def test_save_clears_cache(self, tmp_settings_dir):
        import app.core.system_config as sc
        from app.core.system_config import _save_system_settings, SystemSettings

        sc._settings_cache["data"] = SystemSettings()
        sc._settings_cache["fetched_at"] = time.monotonic()

        _save_system_settings(SystemSettings(portal_base_url="https://new.local"))
        assert sc._settings_cache == {}

    def test_save_writes_json(self, tmp_settings_dir):
        from app.core.system_config import _save_system_settings, SystemSettings

        s = SystemSettings(
            portal_base_url="https://portal.test",
            nc_service_app_password="secret",
        )
        _save_system_settings(s)

        raw = json.loads(tmp_settings_dir["settings_file"].read_text("utf-8"))
        assert raw["portal_base_url"] == "https://portal.test"
        assert raw["nc_service_app_password"] == "secret"

    def test_to_out_masks_password(self, tmp_settings_dir):
        from app.core.system_config import _to_out, SystemSettings

        s = SystemSettings(nc_service_app_password="mysecret")
        out = _to_out(s)
        assert out.nc_service_app_password_set is True
        assert not hasattr(out, "nc_service_app_password")

    def test_to_out_empty_password(self, tmp_settings_dir):
        from app.core.system_config import _to_out, SystemSettings

        s = SystemSettings(nc_service_app_password="")
        out = _to_out(s)
        assert out.nc_service_app_password_set is False


class TestGenerateNginxConfs:
    def test_generates_limits_conf(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(max_upload_size_mb=250, allowed_cidr="10.0.0.0/8")
        generate_nginx_confs(s)

        limits = (tmp_settings_dir["nginx_conf_dir"] / "limits.conf").read_text()
        assert "client_max_body_size 250m" in limits

    def test_generates_allowlist_conf(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(
            max_upload_size_mb=100,
            allowed_cidr="10.10.0.0/16,192.168.5.0/24",
        )
        generate_nginx_confs(s)

        allowlist = (tmp_settings_dir["nginx_conf_dir"] / "allowlist.conf").read_text()
        assert "10.10.0.0/16 1;" in allowlist
        assert "192.168.5.0/24 1;" in allowlist
        assert "127.0.0.1 1;" in allowlist
        assert "default 0;" in allowlist

    def test_single_cidr(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(allowed_cidr="172.16.0.0/12")
        generate_nginx_confs(s)

        allowlist = (tmp_settings_dir["nginx_conf_dir"] / "allowlist.conf").read_text()
        assert "172.16.0.0/12 1;" in allowlist

    def test_empty_cidr_still_allows_loopback(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(allowed_cidr="")
        generate_nginx_confs(s)

        allowlist = (tmp_settings_dir["nginx_conf_dir"] / "allowlist.conf").read_text()
        assert "127.0.0.1 1;" in allowlist


class TestTriggerNginxReload:
    def test_creates_trigger_file(self, tmp_settings_dir):
        from app.core.system_config import trigger_nginx_reload

        trigger = tmp_settings_dir["reload_trigger"]
        assert not trigger.exists()

        trigger_nginx_reload()
        assert trigger.exists()

    def test_trigger_idempotent(self, tmp_settings_dir):
        from app.core.system_config import trigger_nginx_reload

        trigger_nginx_reload()
        trigger_nginx_reload()
        assert tmp_settings_dir["reload_trigger"].exists()


class TestSecretPreservation:
    def test_null_password_keeps_existing(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsIn,
            _save_system_settings,
            load_system_settings,
        )

        _SECRET_MASK = "***"
        existing = SystemSettings(nc_service_app_password="original_secret")
        _save_system_settings(existing)

        body = SystemSettingsIn(
            portal_base_url="https://portal.test",
            nc_service_app_password=None,
        )
        current = load_system_settings()
        nc_password = current.nc_service_app_password
        if body.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = body.nc_service_app_password or ""

        assert nc_password == "original_secret"

    def test_mask_keeps_existing(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsIn,
            _save_system_settings,
            load_system_settings,
        )

        _SECRET_MASK = "***"
        existing = SystemSettings(nc_service_app_password="original_secret")
        _save_system_settings(existing)

        body = SystemSettingsIn(
            portal_base_url="https://portal.test",
            nc_service_app_password=_SECRET_MASK,
        )
        current = load_system_settings()
        nc_password = current.nc_service_app_password
        if body.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = body.nc_service_app_password or ""

        assert nc_password == "original_secret"

    def test_new_value_replaces(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsIn,
            _save_system_settings,
            load_system_settings,
        )

        _SECRET_MASK = "***"
        existing = SystemSettings(nc_service_app_password="original_secret")
        _save_system_settings(existing)

        body = SystemSettingsIn(
            portal_base_url="https://portal.test",
            nc_service_app_password="new_password",
        )
        current = load_system_settings()
        nc_password = current.nc_service_app_password
        if body.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = body.nc_service_app_password or ""

        assert nc_password == "new_password"

    def test_empty_string_clears(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsIn,
            _save_system_settings,
            load_system_settings,
        )

        _SECRET_MASK = "***"
        existing = SystemSettings(nc_service_app_password="original_secret")
        _save_system_settings(existing)

        body = SystemSettingsIn(
            portal_base_url="https://portal.test",
            nc_service_app_password="",
        )
        current = load_system_settings()
        nc_password = current.nc_service_app_password
        if body.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = body.nc_service_app_password or ""

        assert nc_password == ""


class TestSystemSettingsPatch:
    def test_all_fields_default_to_none(self):
        from app.core.system_config import SystemSettingsPatch

        p = SystemSettingsPatch()
        assert p.portal_base_url is None
        assert p.nextcloud_url is None
        assert p.nc_service_app_password is None
        assert p.sentry_dsn is None
        assert p.metrics_token is None
        assert p.video_gallery_url is None

    def test_provided_fields_are_set(self):
        from app.core.system_config import SystemSettingsPatch

        p = SystemSettingsPatch(portal_base_url="https://new.local", max_upload_size_mb=200)
        assert p.portal_base_url == "https://new.local"
        assert p.max_upload_size_mb == 200
        assert p.nextcloud_url is None

    def test_invalid_cidr_raises(self):
        import pytest
        from pydantic import ValidationError
        from app.core.system_config import SystemSettingsPatch

        with pytest.raises(ValidationError, match="Invalid CIDR"):
            SystemSettingsPatch(allowed_cidr="not-a-cidr")

    def test_none_cidr_passes(self):
        from app.core.system_config import SystemSettingsPatch

        p = SystemSettingsPatch(allowed_cidr=None)
        assert p.allowed_cidr is None

    def test_invalid_timezone_raises(self):
        import pytest
        from pydantic import ValidationError
        from app.core.system_config import SystemSettingsPatch

        with pytest.raises(ValidationError, match="Unknown timezone"):
            SystemSettingsPatch(timezone="Not/ATimezone")

    def test_none_timezone_passes(self):
        from app.core.system_config import SystemSettingsPatch

        p = SystemSettingsPatch(timezone=None)
        assert p.timezone is None

    def test_patch_merges_into_current(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsPatch,
            _SECRET_MASK,
            _save_system_settings,
            load_system_settings,
        )

        existing = SystemSettings(
            portal_base_url="https://original.local",
            nextcloud_url="https://nc.local",
            nc_service_app_password="existing_secret",
            max_upload_size_mb=100,
            video_gallery_url="https://video.local",
        )
        _save_system_settings(existing)

        patch = SystemSettingsPatch(video_gallery_url="https://new-video.local")
        current = load_system_settings()

        nc_password = current.nc_service_app_password
        if patch.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = patch.nc_service_app_password or ""

        updated_portal_url = patch.portal_base_url if patch.portal_base_url is not None else current.portal_base_url
        updated_video_url = patch.video_gallery_url if patch.video_gallery_url is not None else current.video_gallery_url

        assert updated_portal_url == "https://original.local"
        assert updated_video_url == "https://new-video.local"
        assert nc_password == "existing_secret"

    def test_patch_secret_null_keeps_existing(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsPatch,
            _SECRET_MASK,
            _save_system_settings,
            load_system_settings,
        )

        existing = SystemSettings(nc_service_app_password="keep_me")
        _save_system_settings(existing)

        patch = SystemSettingsPatch(nc_service_app_password=None)
        current = load_system_settings()

        nc_password = current.nc_service_app_password
        if patch.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = patch.nc_service_app_password or ""

        assert nc_password == "keep_me"

    def test_patch_secret_mask_keeps_existing(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsPatch,
            _SECRET_MASK,
            _save_system_settings,
            load_system_settings,
        )

        existing = SystemSettings(nc_service_app_password="keep_me_too")
        _save_system_settings(existing)

        patch = SystemSettingsPatch(nc_service_app_password=_SECRET_MASK)
        current = load_system_settings()

        nc_password = current.nc_service_app_password
        if patch.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = patch.nc_service_app_password or ""

        assert nc_password == "keep_me_too"

    def test_patch_secret_new_value_updates(self, tmp_settings_dir):
        from app.core.system_config import (
            SystemSettings,
            SystemSettingsPatch,
            _SECRET_MASK,
            _save_system_settings,
            load_system_settings,
        )

        existing = SystemSettings(nc_service_app_password="old_password")
        _save_system_settings(existing)

        patch = SystemSettingsPatch(nc_service_app_password="new_password")
        current = load_system_settings()

        nc_password = current.nc_service_app_password
        if patch.nc_service_app_password not in (None, _SECRET_MASK):
            nc_password = patch.nc_service_app_password or ""

        assert nc_password == "new_password"
