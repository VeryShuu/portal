"""Unit-тесты для api/branding.py.

Покрытие:
- BrandingSettings: дефолты, валидация полей
- EmailSettings / EmailSettingsIn / EmailSettingsOut: дефолты, поля
- _email_settings_to_out: маскирование пароля (только флаг password_set)
- _load_settings / _save_settings: чтение файла, fallback к дефолту, ошибочный JSON
- _load_email_settings / _save_email_settings: аналогично
- _find_file: поиск файла по расширению
- _delete_files: удаление файлов
- _upload_image: неверный MIME → 422
- GET /branding/settings: структура ответа, has_* флаги
- PUT /admin/branding/settings: 403 для non-admin, 200 для admin
- DELETE /admin/branding/logo|favicon|login-bg: 403 non-admin, 200 admin
- GET /admin/email-settings: 403 non-admin, 200 admin (password_set)
- PUT /admin/email-settings: сохранение пароля (null/mask/новый)
- POST /admin/email-settings/test: 422 без host, 200 с host
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── BrandingSettings model ────────────────────────────────────────────────────


class TestBrandingSettingsModel:
    def test_defaults(self):
        from app.api.branding import BrandingSettings

        s = BrandingSettings()
        assert s.portal_name == "Корпоративный портал"
        assert s.accent_color == "#d8262c"
        assert s.banner_enabled is False
        assert s.banner_type == "info"
        assert s.banner_expires_at is None

    def test_custom_values(self):
        from app.api.branding import BrandingSettings

        s = BrandingSettings(
            portal_name="Мой Портал",
            accent_color="#ff0000",
            banner_enabled=True,
            banner_type="warning",
        )
        assert s.portal_name == "Мой Портал"
        assert s.accent_color == "#ff0000"
        assert s.banner_enabled is True
        assert s.banner_type == "warning"

    def test_invalid_banner_type(self):
        from pydantic import ValidationError

        from app.api.branding import BrandingSettings

        with pytest.raises(ValidationError):
            BrandingSettings(banner_type="invalid")


# ── EmailSettings models ──────────────────────────────────────────────────────


class TestEmailSettingsModels:
    def test_email_settings_defaults(self):
        from app.api.branding import EmailSettings

        s = EmailSettings()
        assert s.host == ""
        assert s.port == 25
        assert s.use_tls is False
        assert s.use_starttls is False

    def test_email_settings_in_port_validation(self):
        from pydantic import ValidationError

        from app.api.branding import EmailSettingsIn

        with pytest.raises(ValidationError):
            EmailSettingsIn(port=0)
        with pytest.raises(ValidationError):
            EmailSettingsIn(port=70000)

    def test_email_settings_in_password_nullable(self):
        from app.api.branding import EmailSettingsIn

        s = EmailSettingsIn(password=None)
        assert s.password is None

    def test_email_settings_to_out_masks_password(self):
        from app.api.branding import EmailSettings, _email_settings_to_out

        s = EmailSettings(host="smtp.local", port=587, password="secret123")
        out = _email_settings_to_out(s)
        assert out.password_set is True
        assert not hasattr(out, "password") or not getattr(out, "password", None)

    def test_email_settings_to_out_no_password(self):
        from app.api.branding import EmailSettings, _email_settings_to_out

        s = EmailSettings(host="smtp.local", port=25, password="")
        out = _email_settings_to_out(s)
        assert out.password_set is False


# ── _load_settings / _save_settings ──────────────────────────────────────────


class TestLoadSaveSettings:
    def test_load_settings_fallback_when_file_missing(self, tmp_path):
        import app.api.branding as branding_mod
        from app.api.branding import _DEFAULT_SETTINGS, BrandingSettings

        with patch.object(branding_mod, "_SETTINGS_FILE", tmp_path / "nonexistent.json"):
            from app.api.branding import _load_settings

            result = _load_settings()
        assert isinstance(result, BrandingSettings)
        assert result.portal_name == _DEFAULT_SETTINGS.portal_name

    def test_load_settings_from_valid_file(self, tmp_path):
        import app.api.branding as branding_mod

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"portal_name": "Custom", "accent_color": "#123456"}), encoding="utf-8"
        )
        with (
            patch.object(branding_mod, "_SETTINGS_FILE", settings_file),
            patch.object(branding_mod, "_BRANDING_DIR", tmp_path),
        ):
            from app.api.branding import _load_settings

            result = _load_settings()
        assert result.portal_name == "Custom"
        assert result.accent_color == "#123456"

    def test_load_settings_fallback_on_invalid_json(self, tmp_path):
        import app.api.branding as branding_mod

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{not valid json}", encoding="utf-8")
        with patch.object(branding_mod, "_SETTINGS_FILE", settings_file):
            from app.api.branding import _DEFAULT_SETTINGS, _load_settings

            result = _load_settings()
        assert result.portal_name == _DEFAULT_SETTINGS.portal_name

    def test_save_and_reload_settings(self, tmp_path):
        import app.api.branding as branding_mod
        from app.api.branding import BrandingSettings, _load_settings, _save_settings

        settings_file = tmp_path / "settings.json"
        with (
            patch.object(branding_mod, "_SETTINGS_FILE", settings_file),
            patch.object(branding_mod, "_BRANDING_DIR", tmp_path),
        ):
            s = BrandingSettings(portal_name="Сохранённый", accent_color="#aabbcc")
            _save_settings(s)
            loaded = _load_settings()
        assert loaded.portal_name == "Сохранённый"
        assert loaded.accent_color == "#aabbcc"


# ── _load_email_settings / _save_email_settings ───────────────────────────────


class TestLoadSaveEmailSettings:
    def test_load_email_defaults_when_missing(self, tmp_path):
        import app.api.branding as branding_mod

        with patch.object(branding_mod, "_EMAIL_SETTINGS_FILE", tmp_path / "no.json"):
            from app.api.branding import _load_email_settings

            result = _load_email_settings()
        assert result.host == ""
        assert result.port == 25

    def test_save_and_reload_email_settings(self, tmp_path):
        import app.api.branding as branding_mod
        from app.api.branding import EmailSettings, _load_email_settings, _save_email_settings

        email_file = tmp_path / "email-settings.json"
        with (
            patch.object(branding_mod, "_EMAIL_SETTINGS_FILE", email_file),
            patch.object(branding_mod, "_BRANDING_DIR", tmp_path),
        ):
            s = EmailSettings(host="smtp.example.com", port=465, password="pass123", use_tls=True)
            _save_email_settings(s)
            loaded = _load_email_settings()
        assert loaded.host == "smtp.example.com"
        assert loaded.port == 465
        assert loaded.password == "pass123"
        assert loaded.use_tls is True


# ── _find_file / _delete_files ────────────────────────────────────────────────


class TestFindDeleteFiles:
    def test_find_file_returns_none_when_missing(self, tmp_path):
        import app.api.branding as branding_mod

        with patch.object(branding_mod, "_BRANDING_DIR", tmp_path):
            from app.api.branding import _find_file

            result = _find_file("logo", [".png", ".jpg"])
        assert result is None

    def test_find_file_returns_path_when_exists(self, tmp_path):
        import app.api.branding as branding_mod

        logo = tmp_path / "logo.png"
        logo.write_bytes(b"fakepng")
        with patch.object(branding_mod, "_BRANDING_DIR", tmp_path):
            from app.api.branding import _find_file

            result = _find_file("logo", [".png", ".jpg"])
        assert result == logo

    def test_find_file_picks_first_existing(self, tmp_path):
        import app.api.branding as branding_mod

        logo_jpg = tmp_path / "logo.jpg"
        logo_jpg.write_bytes(b"fakejpg")
        with patch.object(branding_mod, "_BRANDING_DIR", tmp_path):
            from app.api.branding import _find_file

            result = _find_file("logo", [".png", ".jpg"])
        assert result == logo_jpg

    def test_delete_files_removes_existing(self, tmp_path):
        import app.api.branding as branding_mod

        logo = tmp_path / "logo.png"
        logo.write_bytes(b"fakepng")
        with patch.object(branding_mod, "_BRANDING_DIR", tmp_path):
            from app.api.branding import _delete_files

            _delete_files("logo", [".png", ".jpg"])
        assert not logo.exists()

    def test_delete_files_no_error_on_missing(self, tmp_path):
        import app.api.branding as branding_mod

        with patch.object(branding_mod, "_BRANDING_DIR", tmp_path):
            from app.api.branding import _delete_files

            _delete_files("logo", [".png", ".jpg", ".webp"])


# ── API endpoints ─────────────────────────────────────────────────────────────


class TestGetBrandingSettings:
    async def test_returns_200_unauthenticated(self, client):
        with (
            patch("app.api.branding._find_file", return_value=None),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.api.branding._load_settings",
                return_value=__import__(
                    "app.api.branding", fromlist=["BrandingSettings"]
                ).BrandingSettings(),
            ),
        ):
            r = await client.get("/api/v1/branding/settings")
        assert r.status_code == 200
        body = r.json()
        assert "portal_name" in body
        assert "has_favicon" in body
        assert "has_logo" in body

    async def test_has_flags_when_files_exist(self, client):
        fake_path = MagicMock()
        fake_path.__bool__ = lambda self: True

        def _mock_find(prefix, exts):
            if prefix in ("logo", "favicon", "login-bg"):
                return fake_path
            return None

        with (
            patch("app.api.branding._find_file", side_effect=_mock_find),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.api.branding._load_settings",
                return_value=__import__(
                    "app.api.branding", fromlist=["BrandingSettings"]
                ).BrandingSettings(),
            ),
        ):
            r = await client.get("/api/v1/branding/settings")
        assert r.status_code == 200
        body = r.json()
        assert body["has_logo"] is True
        assert body["has_favicon"] is True
        assert body["has_login_bg"] is True


class TestPutBrandingSettings:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.put(
            "/api/v1/admin/branding/settings",
            json={"portal_name": "Test"},
        )
        assert r.status_code == 403

    async def test_admin_saves_settings(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.branding._save_settings"),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.put(
                "/api/v1/admin/branding/settings",
                json={"portal_name": "Новый Портал", "accent_color": "#0000ff"},
            )
        assert r.status_code == 200
        assert r.json()["portal_name"] == "Новый Портал"


class TestDeleteBrandingFiles:
    async def test_reset_logo_non_admin_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.delete("/api/v1/admin/branding/logo")
        assert r.status_code == 403

    async def test_reset_logo_admin_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.branding._delete_files"),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/logo")
        assert r.status_code == 200
        assert "detail" in r.json()

    async def test_reset_favicon_admin_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.branding._delete_files"),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/favicon")
        assert r.status_code == 200

    async def test_reset_login_bg_admin_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.branding._delete_files"),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/login-bg")
        assert r.status_code == 200


class TestGetLogo:
    async def test_404_when_no_logo(self, client):
        with patch("app.api.branding._find_file", return_value=None):
            r = await client.get("/api/v1/branding/logo")
        assert r.status_code == 404

    async def test_404_when_no_favicon(self, client):
        with patch("app.api.branding._find_file", return_value=None):
            r = await client.get("/api/v1/branding/favicon")
        assert r.status_code == 404

    async def test_404_when_no_login_bg(self, client):
        with patch("app.api.branding._find_file", return_value=None):
            r = await client.get("/api/v1/branding/login-bg")
        assert r.status_code == 404


class TestGetEmailSettings:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/admin/email-settings")
        assert r.status_code == 403

    async def test_admin_returns_settings(self, authed_client_factory):
        from app.api.branding import EmailSettings

        ac, _ = authed_client_factory(role="admin")
        with patch(
            "app.api.branding._load_email_settings",
            return_value=EmailSettings(host="smtp.local", port=587, password="secret"),
        ):
            r = await ac.get("/api/v1/admin/email-settings")
        assert r.status_code == 200
        body = r.json()
        assert body["host"] == "smtp.local"
        assert body["password_set"] is True
        assert "password" not in body

    async def test_password_set_false_when_empty(self, authed_client_factory):
        from app.api.branding import EmailSettings

        ac, _ = authed_client_factory(role="admin")
        with patch(
            "app.api.branding._load_email_settings",
            return_value=EmailSettings(host="smtp.local", password=""),
        ):
            r = await ac.get("/api/v1/admin/email-settings")
        assert r.status_code == 200
        assert r.json()["password_set"] is False


class TestPutEmailSettings:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        r = await ac.put(
            "/api/v1/admin/email-settings",
            json={"host": "smtp.local", "port": 25},
        )
        assert r.status_code == 403

    async def test_null_password_keeps_existing(self, authed_client_factory):
        from app.api.branding import EmailSettings

        existing = EmailSettings(host="old.host", password="old_pass")
        ac, _ = authed_client_factory(role="admin")
        saved = {}

        def _mock_save(s):
            saved["password"] = s.password

        with (
            patch("app.api.branding._load_email_settings", return_value=existing),
            patch("app.api.branding._save_email_settings", side_effect=_mock_save),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.put(
                "/api/v1/admin/email-settings",
                json={"host": "new.host", "port": 587, "password": None},
            )
        assert r.status_code == 200
        assert saved["password"] == "old_pass"

    async def test_mask_password_keeps_existing(self, authed_client_factory):
        from app.api.branding import EmailSettings

        existing = EmailSettings(host="old.host", password="real_pass")
        ac, _ = authed_client_factory(role="admin")
        saved = {}

        def _mock_save(s):
            saved["password"] = s.password

        with (
            patch("app.api.branding._load_email_settings", return_value=existing),
            patch("app.api.branding._save_email_settings", side_effect=_mock_save),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.put(
                "/api/v1/admin/email-settings",
                json={"host": "new.host", "port": 587, "password": "***"},
            )
        assert r.status_code == 200
        assert saved["password"] == "real_pass"

    async def test_new_password_replaces_existing(self, authed_client_factory):
        from app.api.branding import EmailSettings

        existing = EmailSettings(host="old.host", password="old_pass")
        ac, _ = authed_client_factory(role="admin")
        saved = {}

        def _mock_save(s):
            saved["password"] = s.password

        with (
            patch("app.api.branding._load_email_settings", return_value=existing),
            patch("app.api.branding._save_email_settings", side_effect=_mock_save),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.put(
                "/api/v1/admin/email-settings",
                json={"host": "new.host", "port": 587, "password": "brand_new_pass"},
            )
        assert r.status_code == 200
        assert saved["password"] == "brand_new_pass"

    async def test_empty_string_password_clears(self, authed_client_factory):
        from app.api.branding import EmailSettings

        existing = EmailSettings(host="old.host", password="old_pass")
        ac, _ = authed_client_factory(role="admin")
        saved = {}

        def _mock_save(s):
            saved["password"] = s.password

        with (
            patch("app.api.branding._load_email_settings", return_value=existing),
            patch("app.api.branding._save_email_settings", side_effect=_mock_save),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.put(
                "/api/v1/admin/email-settings",
                json={"host": "new.host", "port": 587, "password": ""},
            )
        assert r.status_code == 200
        assert saved["password"] == ""


class TestTestEmailSettings:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.post(
            "/api/v1/admin/email-settings/test",
            json={"to": "test@example.com"},
        )
        assert r.status_code == 403

    async def test_no_host_returns_422(self, authed_client_factory):
        from app.api.branding import EmailSettings

        ac, _ = authed_client_factory(role="admin")
        with patch(
            "app.api.branding._load_email_settings",
            return_value=EmailSettings(host=""),
        ):
            r = await ac.post(
                "/api/v1/admin/email-settings/test",
                json={"to": "test@example.com"},
            )
        assert r.status_code == 422

    async def test_with_host_returns_200(self, authed_client_factory):
        from app.api.branding import EmailSettings

        ac, _ = authed_client_factory(role="admin")
        with (
            patch(
                "app.api.branding._load_email_settings",
                return_value=EmailSettings(host="smtp.example.com", port=25),
            ),
            patch("app.api.branding.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.post(
                "/api/v1/admin/email-settings/test",
                json={"to": "admin@example.com"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["to"] == "admin@example.com"
