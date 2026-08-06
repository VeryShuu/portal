"""Unit-тесты для api/branding.py.

Покрытие:
- BrandingSettings: дефолты, валидация полей
- EmailSettings / EmailSettingsIn / EmailSettingsOut: дефолты, поля
- email_settings_to_out: маскирование пароля (только флаг password_set)
- load_settings / save_settings: чтение файла, fallback к дефолту, ошибочный JSON
- load_email_settings / save_email_settings: аналогично
- find_file: поиск файла по расширению
- delete_files: удаление файлов
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
        from app.services.email_settings import EmailSettings, email_settings_to_out

        s = EmailSettings(host="smtp.local", port=587, password="secret123")
        out = email_settings_to_out(s)
        assert out.password_set is True
        assert not hasattr(out, "password") or not getattr(out, "password", None)

    def test_email_settings_to_out_no_password(self):
        from app.services.email_settings import EmailSettings, email_settings_to_out

        s = EmailSettings(host="smtp.local", port=25, password="")
        out = email_settings_to_out(s)
        assert out.password_set is False

    # ── IMAP-блок (ADR-048: общий приёмник почты) ──────────────────────────────

    def test_imap_defaults(self):
        from app.api.branding import EmailSettings

        s = EmailSettings()
        assert s.imap_host == ""
        assert s.imap_port == 993
        assert s.imap_use_ssl is True
        assert s.imap_username == ""
        assert s.imap_password == ""
        assert s.imap_folder == "INBOX"

    def test_imap_to_out_masks_password(self):
        from app.services.email_settings import EmailSettings, email_settings_to_out

        s = EmailSettings(imap_host="imap.local", imap_username="u", imap_password="secret")
        out = email_settings_to_out(s)
        assert out.imap_host == "imap.local"
        assert out.imap_username == "u"
        assert out.imap_password_set is True
        assert not hasattr(out, "imap_password")

    def test_imap_configured_requires_host_username_password(self):
        from app.services.email_settings import EmailSettings, imap_configured

        assert imap_configured(EmailSettings()) is False
        assert imap_configured(EmailSettings(imap_host="h", imap_username="u")) is False
        assert (
            imap_configured(EmailSettings(imap_host="h", imap_username="u", imap_password="p"))
            is True
        )

    def test_imap_password_fernet_roundtrip(self, tmp_path):
        """save→read: imap_password хранится Fernet-шифром (imap_password_enc на
        диске), plaintext не утекает, после reload расшифровывается обратно."""
        import json

        from app.services import email_settings as es_mod
        from app.services.email_settings import (
            EmailSettings,
            load_email_settings,
            save_email_settings,
        )

        f = tmp_path / "email-settings.json"
        with (
            patch.object(es_mod, "EMAIL_SETTINGS_FILE", f),
            patch.object(es_mod, "BRANDING_DIR", tmp_path),
        ):
            save_email_settings(
                EmailSettings(
                    host="smtp.local",
                    password="smtp-pw",
                    imap_host="imap.local",
                    imap_username="u",
                    imap_password="imap-secret",
                    imap_folder="INBOX",
                )
            )

            # На диске — imap_password_enc (Fernet), НЕ plaintext imap_password.
            on_disk = json.loads(f.read_text("utf-8"))
            assert "imap_password_enc" in on_disk
            assert "imap_password" not in on_disk
            # SMTP-пароль остаётся plaintext (намеренно, ADR-048).
            assert on_disk["password"] == "smtp-pw"

            # После reload — imap_password расшифрован обратно, SMTP как есть.
            loaded = load_email_settings()
            assert loaded.imap_password == "imap-secret"
            assert loaded.imap_host == "imap.local"
            assert loaded.password == "smtp-pw"

    def test_imap_password_keep_semantics_on_save(self, tmp_path):
        """load→save без изменений сохраняет тот же imap-пароль (round-trip stable)."""
        from app.services import email_settings as es_mod
        from app.services.email_settings import (
            EmailSettings,
            load_email_settings,
            save_email_settings,
        )

        f = tmp_path / "email-settings.json"
        with (
            patch.object(es_mod, "EMAIL_SETTINGS_FILE", f),
            patch.object(es_mod, "BRANDING_DIR", tmp_path),
        ):
            save_email_settings(
                EmailSettings(imap_host="imap.local", imap_username="u", imap_password="p1")
            )
            # Reload и save без правок — пароль сохраняется.
            s = load_email_settings()
            save_email_settings(s)
            assert load_email_settings().imap_password == "p1"


# ── load_settings / save_settings ──────────────────────────────────────────


class TestLoadSaveSettings:
    def test_load_settings_fallback_when_file_missing(self, tmp_path):
        from app.services.branding_assets import DEFAULT_SETTINGS, BrandingSettings

        with patch("app.services.branding_assets.SETTINGS_FILE", tmp_path / "nonexistent.json"):
            from app.services.branding_assets import load_settings

            result = load_settings()
        assert isinstance(result, BrandingSettings)
        assert result.portal_name == DEFAULT_SETTINGS.portal_name

    def test_load_settings_from_valid_file(self, tmp_path):

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"portal_name": "Custom", "accent_color": "#123456"}), encoding="utf-8"
        )
        with (
            patch("app.services.branding_assets.SETTINGS_FILE", settings_file),
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
        ):
            from app.services.branding_assets import load_settings

            result = load_settings()
        assert result.portal_name == "Custom"
        assert result.accent_color == "#123456"

    def test_load_settings_fallback_on_invalid_json(self, tmp_path):

        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{not valid json}", encoding="utf-8")
        with patch("app.services.branding_assets.SETTINGS_FILE", settings_file):
            from app.services.branding_assets import DEFAULT_SETTINGS, load_settings

            result = load_settings()
        assert result.portal_name == DEFAULT_SETTINGS.portal_name

    def test_save_and_reload_settings(self, tmp_path):
        from app.services.branding_assets import BrandingSettings, load_settings, save_settings

        settings_file = tmp_path / "settings.json"
        with (
            patch("app.services.branding_assets.SETTINGS_FILE", settings_file),
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
        ):
            s = BrandingSettings(portal_name="Сохранённый", accent_color="#aabbcc")
            save_settings(s)
            loaded = load_settings()
        assert loaded.portal_name == "Сохранённый"
        assert loaded.accent_color == "#aabbcc"


# ── load_email_settings / save_email_settings ───────────────────────────────


class TestLoadSaveEmailSettings:
    def test_load_email_defaults_when_missing(self, tmp_path):

        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", tmp_path / "no.json"):
            from app.services.email_settings import load_email_settings

            result = load_email_settings()
        assert result.host == ""
        assert result.port == 25

    def test_save_and_reload_email_settings(self, tmp_path):
        from app.services.email_settings import (
            EmailSettings,
            load_email_settings,
            save_email_settings,
        )

        email_file = tmp_path / "email-settings.json"
        with (
            patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file),
            patch("app.services.email_settings.BRANDING_DIR", tmp_path),
        ):
            s = EmailSettings(host="smtp.example.com", port=465, password="pass123", use_tls=True)
            save_email_settings(s)
            loaded = load_email_settings()
        assert loaded.host == "smtp.example.com"
        assert loaded.port == 465
        assert loaded.password == "pass123"
        assert loaded.use_tls is True


# ── find_file / delete_files ────────────────────────────────────────────────


class TestFindDeleteFiles:
    def test_find_file_returns_none_when_missing(self, tmp_path):

        with patch("app.services.branding_assets.BRANDING_DIR", tmp_path):
            from app.services.branding_assets import find_file

            result = find_file("logo", [".png", ".jpg"])
        assert result is None

    def test_find_file_returns_path_when_exists(self, tmp_path):

        logo = tmp_path / "logo.png"
        logo.write_bytes(b"fakepng")
        with patch("app.services.branding_assets.BRANDING_DIR", tmp_path):
            from app.services.branding_assets import find_file

            result = find_file("logo", [".png", ".jpg"])
        assert result == logo

    def test_find_file_picks_first_existing(self, tmp_path):

        logo_jpg = tmp_path / "logo.jpg"
        logo_jpg.write_bytes(b"fakejpg")
        with patch("app.services.branding_assets.BRANDING_DIR", tmp_path):
            from app.services.branding_assets import find_file

            result = find_file("logo", [".png", ".jpg"])
        assert result == logo_jpg

    def test_delete_files_removes_existing(self, tmp_path):

        logo = tmp_path / "logo.png"
        logo.write_bytes(b"fakepng")
        with patch("app.services.branding_assets.BRANDING_DIR", tmp_path):
            from app.services.branding_assets import delete_files

            delete_files("logo", [".png", ".jpg"])
        assert not logo.exists()

    def test_delete_files_no_error_on_missing(self, tmp_path):

        with patch("app.services.branding_assets.BRANDING_DIR", tmp_path):
            from app.services.branding_assets import delete_files

            delete_files("logo", [".png", ".jpg", ".webp"])


# ── API endpoints ─────────────────────────────────────────────────────────────


class TestGetBrandingSettings:
    async def test_returns_200_unauthenticated(self, client):
        with (
            patch("app.services.branding_assets.find_file", return_value=None),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.services.branding_assets.load_settings",
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
            patch("app.services.branding_assets.find_file", side_effect=_mock_find),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.services.branding_assets.load_settings",
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
            patch("app.services.branding_assets.save_settings"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
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
            patch("app.services.branding_assets.delete_files"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/logo")
        assert r.status_code == 200
        assert "detail" in r.json()

    async def test_reset_favicon_admin_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.delete_files"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/favicon")
        assert r.status_code == 200

    async def test_reset_login_bg_admin_200(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.delete_files"),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.delete("/api/v1/admin/branding/login-bg")
        assert r.status_code == 200


class TestGetLogo:
    async def test_404_when_no_logo(self, client):
        with patch("app.services.branding_assets.find_file", return_value=None):
            r = await client.get("/api/v1/branding/logo")
        assert r.status_code == 404

    async def test_404_when_no_favicon(self, client):
        with patch("app.services.branding_assets.find_file", return_value=None):
            r = await client.get("/api/v1/branding/favicon")
        assert r.status_code == 404

    async def test_404_when_no_login_bg(self, client):
        with patch("app.services.branding_assets.find_file", return_value=None):
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
            "app.services.email_settings.load_email_settings",
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
            "app.services.email_settings.load_email_settings",
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
            patch("app.services.email_settings.load_email_settings", return_value=existing),
            patch("app.services.email_settings.save_email_settings", side_effect=_mock_save),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
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
            patch("app.services.email_settings.load_email_settings", return_value=existing),
            patch("app.services.email_settings.save_email_settings", side_effect=_mock_save),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
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
            patch("app.services.email_settings.load_email_settings", return_value=existing),
            patch("app.services.email_settings.save_email_settings", side_effect=_mock_save),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
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
            patch("app.services.email_settings.load_email_settings", return_value=existing),
            patch("app.services.email_settings.save_email_settings", side_effect=_mock_save),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
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
            "app.services.email_settings.load_email_settings",
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
                "app.services.email_settings.load_email_settings",
                return_value=EmailSettings(host="smtp.example.com", port=25),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            r = await ac.post(
                "/api/v1/admin/email-settings/test",
                json={"to": "admin@example.com"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["to"] == "admin@example.com"


# ── load_email_settings: exception branch ────────────────────────────────────


class TestLoadEmailSettingsCorrupted:
    def test_fallback_on_bad_schema(self, tmp_path):

        email_file = tmp_path / "email-settings.json"
        email_file.write_text('{"port": "not_a_number"}', encoding="utf-8")
        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file):
            from app.services.email_settings import load_email_settings

            result = load_email_settings()
        assert result.host == ""
        assert result.port == 25


# ── save_email_settings: chmod 0o600 ────────────────────────────────────────


class TestSaveEmailSettingsChmod:
    def test_chmod_600_applied(self, tmp_path):
        import stat

        from app.services.email_settings import EmailSettings, save_email_settings

        email_file = tmp_path / "email-settings.json"
        with (
            patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file),
            patch("app.services.email_settings.BRANDING_DIR", tmp_path),
        ):
            save_email_settings(EmailSettings(host="smtp.local", password="secret"))
        mode = email_file.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


# ── GET /branding/settings: logo_updated_at ───────────────────────────────────


class TestLogoUpdatedAt:
    async def test_logo_updated_at_included_when_logo_exists(self, client):
        fake_logo = MagicMock()
        fake_logo.stat.return_value.st_mtime = 1700000000.0

        def _mock_find(prefix, exts):
            if prefix == "logo":
                return fake_logo
            return None

        with (
            patch("app.services.branding_assets.find_file", side_effect=_mock_find),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.services.branding_assets.load_settings",
                return_value=__import__(
                    "app.api.branding", fromlist=["BrandingSettings"]
                ).BrandingSettings(),
            ),
        ):
            r = await client.get("/api/v1/branding/settings")
        assert r.status_code == 200
        assert r.json()["logo_updated_at"] == "1700000000"

    async def test_logo_updated_at_none_when_no_logo(self, client):
        with (
            patch("app.services.branding_assets.find_file", return_value=None),
            patch(
                "app.api.branding.load_system_settings",
                return_value=MagicMock(video_gallery_url=None),
            ),
            patch(
                "app.services.branding_assets.load_settings",
                return_value=__import__(
                    "app.api.branding", fromlist=["BrandingSettings"]
                ).BrandingSettings(),
            ),
        ):
            r = await client.get("/api/v1/branding/settings")
        assert r.status_code == 200
        assert r.json()["logo_updated_at"] is None


# ── HEAD branches for image endpoints ─────────────────────────────────────────


class TestHeadImageEndpoints:
    async def test_head_logo_returns_cache_headers(self, client):
        fake_logo = MagicMock()
        fake_logo.suffix = ".png"
        with patch("app.services.branding_assets.find_file", return_value=fake_logo):
            r = await client.head("/api/v1/branding/logo")
        assert r.status_code == 200
        assert "Cache-Control" in r.headers
        assert "immutable" in r.headers["Cache-Control"]

    async def test_head_logo_404_when_missing(self, client):
        with patch("app.services.branding_assets.find_file", return_value=None):
            r = await client.head("/api/v1/branding/logo")
        assert r.status_code == 404

    async def test_head_favicon_returns_cache_headers(self, client):
        fake_fav = MagicMock()
        fake_fav.suffix = ".ico"
        with patch("app.services.branding_assets.find_file", return_value=fake_fav):
            r = await client.head("/api/v1/branding/favicon")
        assert r.status_code == 200
        assert "Cache-Control" in r.headers

    async def test_head_login_bg_returns_cache_headers(self, client):
        fake_bg = MagicMock()
        fake_bg.suffix = ".jpg"
        with patch("app.services.branding_assets.find_file", return_value=fake_bg):
            r = await client.head("/api/v1/branding/login-bg")
        assert r.status_code == 200
        assert "Cache-Control" in r.headers


# ── POST /admin/branding/logo ─────────────────────────────────────────────────


class TestUploadLogo:
    async def test_invalid_mime_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        files = {"file": ("logo.bmp", b"fakebmp", "image/bmp")}
        r = await ac.post("/api/v1/admin/branding/logo", files=files)
        assert r.status_code == 422

    async def test_upload_png_success_returns_url(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(1024, "image/png"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("logo.png", b"fakepng", "image/png")}
            r = await ac.post("/api/v1/admin/branding/logo", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/logo"

    async def test_upload_jpeg_success_returns_url(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(2048, "image/jpeg"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("logo.jpg", b"fakejpg", "image/jpeg")}
            r = await ac.post("/api/v1/admin/branding/logo", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/logo"

    async def test_non_editor_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        files = {"file": ("logo.png", b"fakepng", "image/png")}
        r = await ac.post("/api/v1/admin/branding/logo", files=files)
        assert r.status_code == 403


# ── POST /admin/branding/favicon ──────────────────────────────────────────────


class TestUploadFavicon:
    async def test_invalid_mime_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        files = {"file": ("favicon.gif", b"fakegif", "image/gif")}
        r = await ac.post("/api/v1/admin/branding/favicon", files=files)
        assert r.status_code == 422

    async def test_upload_ico_success_returns_url(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(256, "image/x-icon"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("favicon.ico", b"fakeico", "image/x-icon")}
            r = await ac.post("/api/v1/admin/branding/favicon", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/favicon"

    async def test_upload_png_favicon_success(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(512, "image/png"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("favicon.png", b"fakepng", "image/png")}
            r = await ac.post("/api/v1/admin/branding/favicon", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/favicon"


# ── POST /admin/branding/login-bg ─────────────────────────────────────────────


class TestUploadLoginBg:
    async def test_invalid_mime_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        files = {"file": ("bg.tiff", b"faketiff", "image/tiff")}
        r = await ac.post("/api/v1/admin/branding/login-bg", files=files)
        assert r.status_code == 422

    async def test_upload_jpeg_success_returns_url(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(1024, "image/jpeg"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("bg.jpg", b"fakejpg", "image/jpeg")}
            r = await ac.post("/api/v1/admin/branding/login-bg", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/login-bg"

    async def test_upload_webp_success_returns_url(self, authed_client_factory, tmp_path):

        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.services.branding_assets.BRANDING_DIR", tmp_path),
            patch(
                "app.services.branding_assets.stream_upload_to_segments",
                new_callable=AsyncMock,
                return_value=(800, "image/webp"),
            ),
            patch("app.services.audit.push_audit_event", new_callable=AsyncMock),
        ):
            files = {"file": ("bg.webp", b"fakewebp", "image/webp")}
            r = await ac.post("/api/v1/admin/branding/login-bg", files=files)
        assert r.status_code == 200
        assert r.json()["url"] == "/api/v1/branding/login-bg"


# ── send_test_email: SMTP kwargs / exception path ───────────────────────────


class TestSendTestEmail:
    async def test_tls_flag_passed_to_smtp(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(host="smtp.example.com", port=465, use_tls=True)
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_test_email(settings=settings, to="user@example.com", sender_name="Admin")
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("use_tls") is True
        assert "start_tls" not in call_kwargs

    async def test_starttls_flag_passed_to_smtp(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(host="smtp.example.com", port=587, use_starttls=True)
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_test_email(settings=settings, to="user@example.com", sender_name="Admin")
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("start_tls") is True
        assert "use_tls" not in call_kwargs

    async def test_credentials_passed_when_both_set(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(
            host="smtp.example.com", port=25, username="user@domain.com", password="s3cr3t"
        )
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_test_email(settings=settings, to="dest@example.com", sender_name="Admin")
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("username") == "user@domain.com"
        assert call_kwargs.get("password") == "s3cr3t"

    async def test_no_credentials_when_password_empty(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(host="smtp.example.com", port=25, username="user", password="")
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_test_email(settings=settings, to="dest@example.com", sender_name="Admin")
        call_kwargs = mock_send.call_args.kwargs
        assert "username" not in call_kwargs
        assert "password" not in call_kwargs

    async def test_base_smtp_kwargs_always_set(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(host="smtp.host.local", port=2525)
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_test_email(settings=settings, to="r@example.com", sender_name="Test")
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["hostname"] == "smtp.host.local"
        assert call_kwargs["port"] == 2525

    async def test_exception_logged_not_raised(self):
        from app.services.email_settings import EmailSettings, send_test_email

        settings = EmailSettings(host="smtp.example.com", port=25)
        with patch("aiosmtplib.send", side_effect=ConnectionRefusedError("refused")):
            await send_test_email(settings=settings, to="user@example.com", sender_name="Admin")


# ── Cross-module SMTP file-format compatibility ───────────────────────────────


class TestEmailSettingsFileCompatibility:
    def test_saved_format_compatible_with_email_utils(self, tmp_path):
        from app.services.email_settings import EmailSettings, save_email_settings
        from app.worker.tasks.email_utils import load_smtp_config

        email_file = tmp_path / "email-settings.json"
        s = EmailSettings(
            host="smtp.example.com",
            port=587,
            from_address="portal@example.com",
            username="user@example.com",
            password="secret_pass",
            use_tls=False,
            use_starttls=True,
        )
        with (
            patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file),
            patch("app.services.email_settings.BRANDING_DIR", tmp_path),
        ):
            save_email_settings(s)

        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file):
            cfg = load_smtp_config()

        assert cfg["host"] == "smtp.example.com"
        assert cfg["port"] == 587
        assert cfg["from_address"] == "portal@example.com"
        assert cfg["username"] == "user@example.com"
        assert cfg["password"] == "secret_pass"
        assert cfg["use_tls"] is False
        assert cfg["use_starttls"] is True

    def test_saved_password_is_plaintext_not_masked(self, tmp_path):
        from app.services.email_settings import (
            EmailSettings,
            load_email_settings,
            save_email_settings,
        )

        email_file = tmp_path / "email-settings.json"
        with (
            patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file),
            patch("app.services.email_settings.BRANDING_DIR", tmp_path),
        ):
            save_email_settings(EmailSettings(host="h", password="original_password"))
            loaded = load_email_settings()
        assert loaded.password == "original_password"

    def test_empty_string_password_persisted_as_empty(self, tmp_path):
        from app.services.email_settings import (
            EmailSettings,
            load_email_settings,
            save_email_settings,
        )

        email_file = tmp_path / "email-settings.json"
        with (
            patch("app.services.email_settings.EMAIL_SETTINGS_FILE", email_file),
            patch("app.services.email_settings.BRANDING_DIR", tmp_path),
        ):
            save_email_settings(EmailSettings(host="h", password=""))
            loaded = load_email_settings()
        assert loaded.password == ""
