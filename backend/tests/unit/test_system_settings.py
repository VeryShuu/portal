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

    def test_ssl_conf_http_only_when_no_certs(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(nextcloud_url="https://nc.company.local")
        generate_nginx_confs(s)

        ssl_conf = (tmp_settings_dir["nginx_conf_dir"] / "ssl_server.conf").read_text()
        assert "listen 80" in ssl_conf
        assert "listen 443" not in ssl_conf
        assert "frame-src 'self' https://nc.company.local" in ssl_conf
        assert "frame-src 'self' https:;" not in ssl_conf
        assert "proxy_hide_header Content-Security-Policy" in ssl_conf

    def test_ssl_conf_https_when_certs_present(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        certs_dir = tmp_settings_dir["certs_dir"]
        (certs_dir / "portal.crt").write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
        (certs_dir / "portal.key").write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n")

        s = SystemSettings(nextcloud_url="https://nc.company.local")
        generate_nginx_confs(s)

        ssl_conf = (tmp_settings_dir["nginx_conf_dir"] / "ssl_server.conf").read_text()
        assert "listen 443 ssl" in ssl_conf
        assert "frame-src 'self' https://nc.company.local" in ssl_conf
        assert "proxy_hide_header Content-Security-Policy" in ssl_conf

    def test_ssl_conf_frame_src_self_only_without_nextcloud(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(nextcloud_url="")
        generate_nginx_confs(s)

        ssl_conf = (tmp_settings_dir["nginx_conf_dir"] / "ssl_server.conf").read_text()
        assert "frame-src 'self';" in ssl_conf
        assert "frame-src 'self' https:" not in ssl_conf

    def test_ssl_conf_no_unsafe_eval(self, tmp_settings_dir):
        from app.core.system_config import generate_nginx_confs, SystemSettings

        s = SystemSettings(nextcloud_url="https://nc.company.local")
        generate_nginx_confs(s)

        ssl_conf = (tmp_settings_dir["nginx_conf_dir"] / "ssl_server.conf").read_text()
        assert "unsafe-eval" not in ssl_conf


class TestBuildNginxCsp:
    def test_includes_nextcloud_origin(self):
        from app.core.system_config import _build_nginx_csp

        csp = _build_nginx_csp("https://nextcloud.company.local")
        assert "frame-src 'self' https://nextcloud.company.local" in csp

    def test_self_only_without_nextcloud(self):
        from app.core.system_config import _build_nginx_csp

        csp = _build_nginx_csp("")
        assert "frame-src 'self';" in csp
        assert "frame-src 'self' https:" not in csp

    def test_no_unsafe_eval(self):
        from app.core.system_config import _build_nginx_csp

        csp = _build_nginx_csp("https://nextcloud.company.local")
        assert "unsafe-eval" not in csp

    def test_script_src_no_unsafe_inline(self):
        from app.core.system_config import _build_nginx_csp

        csp = _build_nginx_csp("")
        script_src_part = csp.split("script-src")[1].split(";")[0]
        assert "unsafe-inline" not in script_src_part

    def test_custom_port_nc_url(self):
        from app.core.system_config import _build_nginx_csp

        csp = _build_nginx_csp("http://nc.internal:8080")
        assert "frame-src 'self' http://nc.internal:8080" in csp

    def test_no_open_https_wildcard(self):
        from app.core.system_config import _build_nginx_csp

        for url in ["", "https://nc.local", "http://nc.internal:8080"]:
            csp = _build_nginx_csp(url)
            assert "frame-src 'self' https:;" not in csp


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


class TestTlsCertUpload:
    """API-тесты для POST /admin/system/tls/cert (4.7)."""

    _VALID_CERT = (
        b"-----BEGIN CERTIFICATE-----\n"
        b"MIIBIjANBgkqhkiG9w0BAQEFAAOBjQAMIIBCgKCAQEA2\n"
        b"-----END CERTIFICATE-----\n"
    )

    async def test_non_admin_gets_403(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.post(
                "/api/v1/admin/system/tls/cert",
                files={"file": ("portal.crt", self._VALID_CERT, "application/x-pem-file")},
            )
            assert r.status_code == 403, f"Expected 403 for role={role}"

    async def test_valid_pem_cert_returns_200(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import AsyncMock, patch

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]),
            patch("app.api.system_settings.generate_ssl_server_conf"),
            patch("app.api.system_settings.trigger_nginx_reload"),
            patch("app.api.system_settings.push_audit_event", new_callable=AsyncMock),
            patch("app.api.system_settings.load_system_settings", return_value=__import__(
                "app.core.system_config", fromlist=["SystemSettings"]
            ).SystemSettings()),
        ):
            r = await ac.post(
                "/api/v1/admin/system/tls/cert",
                files={"file": ("portal.crt", self._VALID_CERT, "application/x-pem-file")},
            )
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_non_pem_content_returns_400(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        binary_garbage = b"\x00\x01\x02\x03this is not a certificate"
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/cert",
                files={"file": ("bad.crt", binary_garbage, "application/octet-stream")},
            )
        assert r.status_code == 400
        assert "PEM" in r.json()["detail"]

    async def test_oversized_cert_returns_400(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        oversized = b"-----BEGIN CERTIFICATE-----\n" + b"A" * (64 * 1024 + 10)
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/cert",
                files={"file": ("big.crt", oversized, "application/x-pem-file")},
            )
        assert r.status_code == 400
        assert "64" in r.json()["detail"]

    async def test_csr_content_returns_400(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        csr_content = b"-----BEGIN CERTIFICATE REQUEST-----\nfake\n-----END CERTIFICATE REQUEST-----\n"
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/cert",
                files={"file": ("req.csr", csr_content, "application/x-pem-file")},
            )
        assert r.status_code == 400
        assert "PEM" in r.json()["detail"]


class TestTlsKeyUpload:
    """API-тесты для POST /admin/system/tls/key (4.7)."""

    _VALID_KEY = (
        b"-----BEGIN PRIVATE KEY-----\n"
        b"MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEA\n"
        b"-----END PRIVATE KEY-----\n"
    )

    async def test_non_admin_gets_403(self, authed_client_factory):
        for role in ("reader", "editor"):
            ac, _ = authed_client_factory(role=role)
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("portal.key", self._VALID_KEY, "application/x-pem-file")},
            )
            assert r.status_code == 403, f"Expected 403 for role={role}"

    async def test_valid_pem_key_returns_200(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import AsyncMock, patch

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]),
            patch("app.api.system_settings.generate_ssl_server_conf"),
            patch("app.api.system_settings.trigger_nginx_reload"),
            patch("app.api.system_settings.push_audit_event", new_callable=AsyncMock),
            patch("app.api.system_settings.load_system_settings", return_value=__import__(
                "app.core.system_config", fromlist=["SystemSettings"]
            ).SystemSettings()),
        ):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("portal.key", self._VALID_KEY, "application/x-pem-file")},
            )
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_non_pem_content_returns_400(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        garbage = b"\xff\xfe not a key at all"
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("bad.key", garbage, "application/octet-stream")},
            )
        assert r.status_code == 400
        assert "PEM" in r.json()["detail"]

    async def test_oversized_key_returns_400(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        oversized = b"-----BEGIN PRIVATE KEY-----\n" + b"B" * (64 * 1024 + 10)
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("big.key", oversized, "application/x-pem-file")},
            )
        assert r.status_code == 400
        assert "64" in r.json()["detail"]

    async def test_certificate_uploaded_as_key_returns_400(self, authed_client_factory, tmp_settings_dir):
        """Сертификат не должен приниматься как приватный ключ."""
        from unittest.mock import patch

        ac, _ = authed_client_factory(role="admin")
        cert_as_key = b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n"
        with patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("wrong.key", cert_as_key, "application/x-pem-file")},
            )
        assert r.status_code == 400
        assert "PEM" in r.json()["detail"]

    async def test_rsa_private_key_header_accepted(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import AsyncMock, patch

        ac, _ = authed_client_factory(role="admin")
        rsa_key = b"-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n"
        with (
            patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]),
            patch("app.api.system_settings.generate_ssl_server_conf"),
            patch("app.api.system_settings.trigger_nginx_reload"),
            patch("app.api.system_settings.push_audit_event", new_callable=AsyncMock),
            patch("app.api.system_settings.load_system_settings", return_value=__import__(
                "app.core.system_config", fromlist=["SystemSettings"]
            ).SystemSettings()),
        ):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("portal.key", rsa_key, "application/x-pem-file")},
            )
        assert r.status_code == 200

    async def test_ec_private_key_header_accepted(self, authed_client_factory, tmp_settings_dir):
        from unittest.mock import AsyncMock, patch

        ac, _ = authed_client_factory(role="admin")
        ec_key = b"-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----\n"
        with (
            patch("app.api.system_settings._CERTS_DIR", tmp_settings_dir["certs_dir"]),
            patch("app.api.system_settings.generate_ssl_server_conf"),
            patch("app.api.system_settings.trigger_nginx_reload"),
            patch("app.api.system_settings.push_audit_event", new_callable=AsyncMock),
            patch("app.api.system_settings.load_system_settings", return_value=__import__(
                "app.core.system_config", fromlist=["SystemSettings"]
            ).SystemSettings()),
        ):
            r = await ac.post(
                "/api/v1/admin/system/tls/key",
                files={"file": ("portal.key", ec_key, "application/x-pem-file")},
            )
        assert r.status_code == 200
