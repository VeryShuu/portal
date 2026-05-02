"""Unit-тесты для services/keycloak.py.

Покрытие:
- _KCSettings: инициализация, trailing slash у URL
- _get_kc_settings: приоритет файла над .env, TTL кэша, fallback
- invalidate_settings_cache: сброс кэша
- get_authorization_url: структура URL (параметры PKCE)
- get_silent_auth_url: prompt=none
- get_logout_url: post_logout_redirect_uri, опциональный id_token_hint
- _oidc_base: формирование базового OIDC URL
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── _KCSettings ───────────────────────────────────────────────────────────────


class TestKCSettings:
    def test_strips_trailing_slash_from_url(self):
        from app.services.keycloak import _KCSettings

        kc = _KCSettings(
            keycloak_url="http://keycloak:8080/",
            keycloak_realm="master",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        assert not kc.keycloak_url.endswith("/")
        assert kc.keycloak_url == "http://keycloak:8080"

    def test_sync_credentials_optional(self):
        from app.services.keycloak import _KCSettings

        kc = _KCSettings(
            keycloak_url="http://kc",
            keycloak_realm="r",
            oidc_client_id="c",
            oidc_client_secret="s",
        )
        assert kc.sync_client_id == ""
        assert kc.sync_client_secret == ""

    def test_full_init(self):
        from app.services.keycloak import _KCSettings

        kc = _KCSettings(
            keycloak_url="http://kc",
            keycloak_realm="myrealm",
            oidc_client_id="portal",
            oidc_client_secret="sec",
            sync_client_id="sync",
            sync_client_secret="syncsec",
        )
        assert kc.keycloak_realm == "myrealm"
        assert kc.sync_client_id == "sync"


# ── _get_kc_settings ──────────────────────────────────────────────────────────


class TestGetKCSettings:
    def setup_method(self):
        from app.services.keycloak import invalidate_settings_cache

        invalidate_settings_cache()

    def test_returns_env_fallback_when_file_missing(self, tmp_path):
        import app.services.keycloak as kc_mod

        fake_settings = MagicMock()
        fake_settings.keycloak_url = "http://env-kc:8080"
        fake_settings.keycloak_realm = "env-realm"
        fake_settings.keycloak_client_id = "env-client"
        fake_settings.keycloak_client_secret = "env-secret"

        with (
            patch.object(kc_mod, "_KC_SETTINGS_FILE", tmp_path / "no.json"),
            patch.object(kc_mod, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "no-legacy.json"),
            patch.object(kc_mod, "settings", fake_settings),
            patch.object(kc_mod, "_settings_cache", {}),
        ):
            from app.services.keycloak import _get_kc_settings

            result = _get_kc_settings()
        assert result.keycloak_url == "http://env-kc:8080"
        assert result.keycloak_realm == "env-realm"

    def test_loads_from_file(self, tmp_path):
        import app.services.keycloak as kc_mod

        kc_file = tmp_path / "keycloak-settings.json"
        kc_file.write_text(
            json.dumps({
                "keycloak_url": "http://file-kc:8080",
                "keycloak_realm": "file-realm",
                "oidc_client_id": "file-client",
                "oidc_client_secret": "file-secret",
            }),
            encoding="utf-8",
        )

        fake_settings = MagicMock()
        fake_settings.keycloak_url = "http://env-kc"
        fake_settings.keycloak_realm = "env-realm"
        fake_settings.keycloak_client_id = "env-client"
        fake_settings.keycloak_client_secret = "env-secret"

        with (
            patch.object(kc_mod, "_KC_SETTINGS_FILE", kc_file),
            patch.object(kc_mod, "settings", fake_settings),
            patch.object(kc_mod, "_settings_cache", {}),
        ):
            from app.services.keycloak import _get_kc_settings

            result = _get_kc_settings()
        assert result.keycloak_url == "http://file-kc:8080"
        assert result.keycloak_realm == "file-realm"

    def test_cache_hit_returns_cached(self, tmp_path):
        import app.services.keycloak as kc_mod
        from app.services.keycloak import _KCSettings

        cached = _KCSettings("http://cached", "cached-realm", "c", "s")
        cache = {"data": cached, "fetched_at": time.monotonic()}

        with patch.object(kc_mod, "_settings_cache", cache):
            from app.services.keycloak import _get_kc_settings

            result = _get_kc_settings()
        assert result.keycloak_url == "http://cached"

    def test_invalidate_clears_cache(self):
        import app.services.keycloak as kc_mod

        kc_mod._settings_cache["data"] = MagicMock()
        kc_mod._settings_cache["fetched_at"] = time.monotonic()

        from app.services.keycloak import invalidate_settings_cache

        invalidate_settings_cache()
        assert not kc_mod._settings_cache


# ── URL builders ──────────────────────────────────────────────────────────────


class TestGetAuthorizationUrl:
    def _make_kc(self):
        from app.services.keycloak import _KCSettings

        return _KCSettings(
            keycloak_url="http://kc:8080",
            keycloak_realm="myrealm",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )

    def test_contains_required_params(self):
        from app.services.keycloak import get_authorization_url

        kc = self._make_kc()
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_authorization_url(
                redirect_uri="http://portal/callback",
                state="state123",
                nonce="nonce456",
                code_challenge="challenge789",
            )
        assert "response_type=code" in url
        assert "client_id=portal" in url
        assert "state=state123" in url
        assert "nonce=nonce456" in url
        assert "code_challenge=challenge789" in url
        assert "code_challenge_method=S256" in url
        assert "myrealm" in url

    def test_url_starts_with_keycloak_base(self):
        from app.services.keycloak import get_authorization_url

        kc = self._make_kc()
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_authorization_url(
                redirect_uri="http://p/cb",
                state="s",
                nonce="n",
                code_challenge="c",
            )
        assert url.startswith("http://kc:8080/realms/myrealm/protocol/openid-connect/auth")


class TestGetSilentAuthUrl:
    def test_contains_prompt_none(self):
        from app.services.keycloak import _KCSettings, get_silent_auth_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_silent_auth_url(
                redirect_uri="http://portal/cb",
                state="st",
                nonce="nn",
            )
        assert "prompt=none" in url
        assert "response_type=code" in url

    def test_does_not_contain_code_challenge(self):
        from app.services.keycloak import _KCSettings, get_silent_auth_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_silent_auth_url(
                redirect_uri="http://portal/cb",
                state="st",
                nonce="nn",
            )
        assert "code_challenge" not in url


class TestGetLogoutUrl:
    def test_contains_post_logout_redirect(self):
        from app.services.keycloak import _KCSettings, get_logout_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_logout_url(post_logout_redirect_uri="http://portal/")
        assert "post_logout_redirect_uri=http://portal/" in url
        assert "client_id=client" in url

    def test_with_id_token_hint(self):
        from app.services.keycloak import _KCSettings, get_logout_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_logout_url(
                post_logout_redirect_uri="http://portal/",
                id_token_hint="token123",
            )
        assert "id_token_hint=token123" in url

    def test_without_id_token_hint(self):
        from app.services.keycloak import _KCSettings, get_logout_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_logout_url(post_logout_redirect_uri="http://portal/")
        assert "id_token_hint" not in url

    def test_url_ends_with_logout(self):
        from app.services.keycloak import _KCSettings, get_logout_url

        kc = _KCSettings("http://kc", "realm", "client", "secret")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            url = get_logout_url(post_logout_redirect_uri="http://portal/")
        assert "/logout?" in url


# ── _oidc_base ────────────────────────────────────────────────────────────────


class TestOidcBase:
    def test_oidc_base_format(self):
        from app.services.keycloak import _KCSettings, _oidc_base

        kc = _KCSettings("http://kc:8080", "myrealm", "c", "s")
        with patch("app.services.keycloak._get_kc_settings", return_value=kc):
            base = _oidc_base()
        assert base == "http://kc:8080/realms/myrealm/protocol/openid-connect"
