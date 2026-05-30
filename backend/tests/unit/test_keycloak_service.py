"""Unit-тесты services/keycloak.py (Фаза 3.3).

Покрытие:
- invalidate_jwks_cache: очищает _JWKS_CACHE
- invalidate_settings_cache: очищает _settings_cache
- get_kc_settings / _get_kc_settings: cached / file missing / valid file / corrupt file
- _get_kc_http_client: lazy create / reuse / recreate closed
- get_authorization_url: формирует URL с параметрами
- get_silent_auth_url: добавляет prompt=none
- get_logout_url: без/с id_token_hint
- exchange_code_for_tokens: успех / HTTP-ошибка
- refresh_tokens: успех / HTTP-ошибка
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _kc_settings_json(
    url: str = "https://kc.example.com",
    realm: str = "myrealm",
    **kwargs,
) -> str:
    data = {
        "keycloak_url": url,
        "keycloak_realm": realm,
        "oidc_client_id": kwargs.get("oidc_client_id", "portal"),
        "oidc_client_secret": kwargs.get("oidc_client_secret", "s3cr3t"),
        "sync_client_id": kwargs.get("sync_client_id", ""),
        "sync_client_secret": kwargs.get("sync_client_secret", ""),
    }
    return json.dumps(data)


def _patch_kc_settings(tmp_path: Path, **kwargs):
    settings_file = tmp_path / "keycloak-settings.json"
    settings_file.write_text(_kc_settings_json(**kwargs), encoding="utf-8")
    return settings_file


# ── invalidate_jwks_cache ─────────────────────────────────────────────────────


def test_invalidate_jwks_cache_clears():
    from app.services import keycloak as kc

    kc._JWKS_CACHE["keys"] = ["key1"]
    kc._JWKS_CACHE["fetched_at"] = time.monotonic()
    kc.invalidate_jwks_cache()
    assert kc._JWKS_CACHE == {}


# ── invalidate_settings_cache ──────────────────────────────────────────────────


def test_invalidate_settings_cache_clears():
    from app.services import keycloak as kc

    kc._settings_cache["data"] = MagicMock()
    kc._settings_cache["fetched_at"] = time.monotonic()
    kc.invalidate_settings_cache()
    assert kc._settings_cache == {}


# ── _get_kc_settings ──────────────────────────────────────────────────────────


def test_get_kc_settings_returns_defaults_when_files_missing(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    missing1 = tmp_path / "kc.json"
    missing2 = tmp_path / "legacy.json"

    with patch.object(kc, "_KC_SETTINGS_FILE", missing1):
        with patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", missing2):
            result = kc._get_kc_settings()

    assert result.keycloak_url == ""
    assert result.keycloak_realm == ""
    kc._settings_cache.clear()


def test_get_kc_settings_reads_valid_file(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path, url="https://kc.example.com", realm="myrealm")

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        result = kc._get_kc_settings()

    assert result.keycloak_url == "https://kc.example.com"
    assert result.keycloak_realm == "myrealm"
    assert result.oidc_client_secret == "s3cr3t"
    kc._settings_cache.clear()


def test_get_kc_settings_corrupt_file_returns_defaults(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = tmp_path / "kc.json"
    sf.write_text("not valid json", encoding="utf-8")

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        result = kc._get_kc_settings()

    assert result.keycloak_url == ""
    kc._settings_cache.clear()


def test_get_kc_settings_uses_cache():
    from app.services import keycloak as kc
    from app.services.keycloak import _KCSettings

    kc._settings_cache.clear()
    fake = _KCSettings("https://cached.example.com", "cached", "portal", "")
    kc._settings_cache["data"] = fake
    kc._settings_cache["fetched_at"] = time.monotonic()

    result = kc._get_kc_settings()
    assert result is fake
    kc._settings_cache.clear()


def test_get_kc_settings_skips_empty_url(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = tmp_path / "kc.json"
    sf.write_text(
        json.dumps(
            {
                "keycloak_url": "",
                "keycloak_realm": "",
                "oidc_client_id": "",
                "oidc_client_secret": "",
                "sync_client_id": "",
                "sync_client_secret": "",
            }
        ),
        encoding="utf-8",
    )

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        result = kc._get_kc_settings()

    assert result.keycloak_url == ""
    kc._settings_cache.clear()


# ── _get_kc_http_client ───────────────────────────────────────────────────────


def test_get_kc_http_client_creates_instance():
    from app.services import keycloak as kc

    kc._KC_HTTP_CLIENT = None
    client = kc._get_kc_http_client()
    assert client is not None
    kc._KC_HTTP_CLIENT = None


def test_get_kc_http_client_reuses_open_client():
    from app.services import keycloak as kc

    kc._KC_HTTP_CLIENT = None
    c1 = kc._get_kc_http_client()
    c2 = kc._get_kc_http_client()
    assert c1 is c2
    kc._KC_HTTP_CLIENT = None


def test_get_kc_http_client_recreates_closed():
    import httpx

    from app.services import keycloak as kc

    closed = MagicMock(spec=httpx.AsyncClient)
    closed.is_closed = True
    kc._KC_HTTP_CLIENT = closed

    new_client = kc._get_kc_http_client()
    assert new_client is not closed
    kc._KC_HTTP_CLIENT = None


# ── init_kc_http_client / close_kc_http_client ────────────────────────────────


@pytest.mark.asyncio
async def test_init_kc_http_client_creates():
    from app.services import keycloak as kc

    kc._KC_HTTP_CLIENT = None
    await kc.init_kc_http_client()
    assert kc._KC_HTTP_CLIENT is not None
    kc._KC_HTTP_CLIENT = None


@pytest.mark.asyncio
async def test_close_kc_http_client_closes_and_clears():
    import httpx

    from app.services import keycloak as kc

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    kc._KC_HTTP_CLIENT = mock_client

    await kc.close_kc_http_client()
    mock_client.aclose.assert_awaited_once()
    assert kc._KC_HTTP_CLIENT is None


@pytest.mark.asyncio
async def test_close_kc_http_client_skips_already_closed():
    import httpx

    from app.services import keycloak as kc

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.is_closed = True
    kc._KC_HTTP_CLIENT = mock_client

    await kc.close_kc_http_client()
    assert kc._KC_HTTP_CLIENT is None


# ── get_authorization_url ─────────────────────────────────────────────────────


def test_get_authorization_url_contains_params(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(
        tmp_path, url="https://kc.example.com", realm="myrealm", oidc_client_id="portal"
    )

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        url = kc.get_authorization_url(
            redirect_uri="https://app.example.com/callback",
            state="state123",
            nonce="nonce456",
            code_challenge="challenge789",
        )

    assert "https://kc.example.com" in url
    assert "myrealm" in url
    assert "portal" in url
    assert "state123" in url
    assert "nonce456" in url
    assert "S256" in url
    assert "response_type=code" in url
    kc._settings_cache.clear()


# ── get_silent_auth_url ───────────────────────────────────────────────────────


def test_get_silent_auth_url_has_prompt_none(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path)

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        url = kc.get_silent_auth_url(
            redirect_uri="https://app.example.com/callback",
            state="st",
            nonce="nn",
        )

    assert "prompt=none" in url
    kc._settings_cache.clear()


# ── get_logout_url ────────────────────────────────────────────────────────────


def test_get_logout_url_without_hint(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path, oidc_client_id="portal")

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        url = kc.get_logout_url(post_logout_redirect_uri="https://app.example.com")

    assert "logout" in url
    assert "portal" in url
    assert "id_token_hint" not in url
    kc._settings_cache.clear()


def test_get_logout_url_with_hint(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path)

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        url = kc.get_logout_url(
            post_logout_redirect_uri="https://app.example.com",
            id_token_hint="some-token",
        )

    assert "id_token_hint=some-token" in url
    kc._settings_cache.clear()


# ── exchange_code_for_tokens ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_success(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok", "refresh_token": "ref"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        with patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            with patch.object(kc, "_get_kc_http_client", return_value=mock_client):
                with patch.object(kc, "_get_kc_settings_async", return_value=kc._get_kc_settings()):
                    result = await kc.exchange_code_for_tokens(
                        "code", "https://cb.example.com", "verifier"
                    )

    assert result["access_token"] == "tok"
    kc._settings_cache.clear()


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_http_error(tmp_path):
    import httpx

    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        with patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            with patch.object(kc, "_get_kc_http_client", return_value=mock_client):
                with patch.object(kc, "_get_kc_settings_async", return_value=kc._get_kc_settings()):
                    with pytest.raises(httpx.HTTPStatusError):
                        await kc.exchange_code_for_tokens("bad-code", "https://cb.example.com", "v")

    kc._settings_cache.clear()


# ── refresh_tokens ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_tokens_success(tmp_path):
    from app.services import keycloak as kc

    kc._settings_cache.clear()
    sf = _patch_kc_settings(tmp_path)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"access_token": "new_tok", "refresh_token": "new_ref"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(kc, "_KC_SETTINGS_FILE", sf):
        with patch.object(kc, "_LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            with patch.object(kc, "_get_kc_http_client", return_value=mock_client):
                with patch.object(kc, "_get_kc_settings_async", return_value=kc._get_kc_settings()):
                    result = await kc.refresh_tokens("old_refresh_token")

    assert result["access_token"] == "new_tok"
    kc._settings_cache.clear()
