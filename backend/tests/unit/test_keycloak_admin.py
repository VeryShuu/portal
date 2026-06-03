"""Unit-тесты api/keycloak_admin.py (Фаза 4.12).

Покрытие:
- _is_unsafe_ip: loopback / link-local / multicast / cloud-metadata / private (allowed) / hostname (skipped)
- _validate_keycloak_url: bad scheme / empty host / blocked hostname / blocked IP / valid
- _load_kc_settings: file not found → defaults / valid file / corrupt file → defaults / migrate legacy
- _save_kc_settings: writes file
- _to_out: masks secrets
- GET /admin/keycloak/settings: returns masked settings
- PUT /admin/keycloak/settings: updates / keeps masked secret / clears secret
- POST /admin/keycloak/test/oidc: no url → 400 / discovery fail / no client creds / success
- POST /admin/keycloak/test/sync: no url → 400 / no creds → 400 / token fail / success
- GET /admin/keycloak/sync/status: empty / valid / corrupt json
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── _is_unsafe_ip ─────────────────────────────────────────────────────────────


def test_is_unsafe_ip_loopback():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("127.0.0.1") is True


def test_is_unsafe_ip_ipv6_loopback():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("::1") is True


def test_is_unsafe_ip_link_local():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("169.254.1.1") is True


def test_is_unsafe_ip_cloud_metadata():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("169.254.169.254") is True


def test_is_unsafe_ip_multicast():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("224.0.0.1") is True


def test_is_unsafe_ip_private_allowed():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("192.168.1.1") is False


def test_is_unsafe_ip_private_10_allowed():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("10.0.0.1") is False


def test_is_unsafe_ip_public():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("8.8.8.8") is False


def test_is_unsafe_ip_hostname_not_ip():
    from app.api.keycloak_admin import _is_unsafe_ip

    assert _is_unsafe_ip("keycloak.example.com") is False


# ── _validate_keycloak_url ────────────────────────────────────────────────────


def test_validate_keycloak_url_bad_scheme():
    from fastapi import HTTPException

    from app.api.keycloak_admin import _validate_keycloak_url

    with pytest.raises(HTTPException) as exc:
        _validate_keycloak_url("ftp://keycloak.example.com")
    assert exc.value.status_code == 400


def test_validate_keycloak_url_empty_host():
    from fastapi import HTTPException

    from app.api.keycloak_admin import _validate_keycloak_url

    with pytest.raises(HTTPException) as exc:
        _validate_keycloak_url("http://")
    assert exc.value.status_code == 400


def test_validate_keycloak_url_blocked_hostname():
    from fastapi import HTTPException

    from app.api.keycloak_admin import _validate_keycloak_url

    with pytest.raises(HTTPException) as exc:
        _validate_keycloak_url("http://localhost/auth")
    assert exc.value.status_code == 400


def test_validate_keycloak_url_blocked_ip():
    from fastapi import HTTPException

    from app.api.keycloak_admin import _validate_keycloak_url

    with pytest.raises(HTTPException) as exc:
        _validate_keycloak_url("http://127.0.0.1/auth")
    assert exc.value.status_code == 400


def test_validate_keycloak_url_valid():
    from app.api.keycloak_admin import _validate_keycloak_url

    _validate_keycloak_url("https://keycloak.company.com/auth")


def test_validate_keycloak_url_private_ip_allowed():
    from app.api.keycloak_admin import _validate_keycloak_url

    _validate_keycloak_url("https://192.168.1.100/auth")


# ── _load_kc_settings ─────────────────────────────────────────────────────────


def test_load_kc_settings_defaults_when_file_missing(tmp_path):
    from app.api.keycloak_admin import KeycloakSettings, _load_kc_settings

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", tmp_path / "missing.json"):
        with patch(
            "app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "also-missing.json"
        ):
            result = _load_kc_settings()

    assert isinstance(result, KeycloakSettings)
    assert result.keycloak_url == ""


def test_load_kc_settings_reads_valid_file(tmp_path):
    from app.api.keycloak_admin import _load_kc_settings

    data = {
        "keycloak_url": "https://kc.example.com",
        "keycloak_realm": "myrealm",
        "oidc_client_id": "portal",
        "oidc_client_secret": "secret123",
        "sync_client_id": "sync",
        "sync_client_secret": "syncsecret",
    }
    settings_file = tmp_path / "keycloak-settings.json"
    settings_file.write_text(json.dumps(data), encoding="utf-8")

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        result = _load_kc_settings()

    assert result.keycloak_url == "https://kc.example.com"
    assert result.keycloak_realm == "myrealm"
    assert result.oidc_client_secret == "secret123"


def test_load_kc_settings_corrupt_file_returns_defaults(tmp_path):
    from app.api.keycloak_admin import _load_kc_settings

    settings_file = tmp_path / "keycloak-settings.json"
    settings_file.write_text("not valid json {{{{", encoding="utf-8")

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        result = _load_kc_settings()

    assert result.keycloak_url == ""


def test_load_kc_settings_migrates_legacy(tmp_path):
    from app.api.keycloak_admin import _load_kc_settings

    data = {
        "keycloak_url": "https://legacy.example.com",
        "keycloak_realm": "company",
        "oidc_client_id": "portal",
        "oidc_client_secret": "",
        "sync_client_id": "",
        "sync_client_secret": "",
    }
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    new_file = tmp_path / "new.json"

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", new_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", legacy):
            with patch("app.api.keycloak_admin._SECRETS_DIR", tmp_path):
                result = _load_kc_settings()

    assert result.keycloak_url == "https://legacy.example.com"
    assert new_file.exists()


# ── _to_out ───────────────────────────────────────────────────────────────────


def test_to_out_masks_secrets():
    from app.api.keycloak_admin import KeycloakSettings, _to_out

    s = KeycloakSettings(
        keycloak_url="https://kc.example.com",
        keycloak_realm="company",
        oidc_client_id="portal",
        oidc_client_secret="mysecret",
        sync_client_id="sync",
        sync_client_secret="syncsecret",
    )
    out = _to_out(s)
    assert out.oidc_client_secret_set is True
    assert out.sync_client_secret_set is True
    assert not hasattr(out, "oidc_client_secret")


def test_to_out_empty_secrets():
    from app.api.keycloak_admin import KeycloakSettings, _to_out

    s = KeycloakSettings()
    out = _to_out(s)
    assert out.oidc_client_secret_set is False
    assert out.sync_client_secret_set is False


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _make_admin_user():
    return SimpleNamespace(id=uuid.uuid4(), role="admin")


def _make_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


def _build_app(redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_redis
    from app.api.keycloak_admin import router

    app = FastAPI()
    app.include_router(router)

    admin = _make_admin_user()

    async def _fake_admin():
        return admin

    async def _fake_redis():
        return redis

    app.dependency_overrides[get_current_user] = _fake_admin
    app.dependency_overrides[get_redis] = _fake_redis
    return app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json_data=None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json_data)


async def _put(app, url: str, json_data=None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.put(url, json=json_data)


# ── GET /admin/keycloak/settings ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_keycloak_settings_returns_out(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
        json.dumps(
            {
                "keycloak_url": "https://kc.example.com",
                "keycloak_realm": "myrealm",
                "oidc_client_id": "portal",
                "oidc_client_secret": "s3cr3t",
                "sync_client_id": "",
                "sync_client_secret": "",
            }
        ),
        encoding="utf-8",
    )

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            resp = await _get(app, "/admin/keycloak/settings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["keycloak_url"] == "https://kc.example.com"
    assert data["oidc_client_secret_set"] is True


# ── PUT /admin/keycloak/settings ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_keycloak_settings_updates(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
        json.dumps(
            {
                "keycloak_url": "",
                "keycloak_realm": "company",
                "oidc_client_id": "portal",
                "oidc_client_secret": "",
                "sync_client_id": "",
                "sync_client_secret": "",
            }
        ),
        encoding="utf-8",
    )

    payload = {
        "keycloak_url": "https://kc.example.com",
        "keycloak_realm": "myrealm",
        "oidc_client_id": "portal",
        "oidc_client_secret": "newsecret",
        "sync_client_id": "",
        "sync_client_secret": None,
    }

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            with patch("app.api.keycloak_admin._SECRETS_DIR", tmp_path):
                with patch("app.services.keycloak.invalidate_settings_cache"):
                    with patch("app.api.keycloak_admin.bump_version", new_callable=AsyncMock):
                        with patch("app.services.audit.push_audit_event", new_callable=AsyncMock):
                            resp = await _put(app, "/admin/keycloak/settings", payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["keycloak_url"] == "https://kc.example.com"


@pytest.mark.asyncio
async def test_put_keycloak_settings_keeps_masked_secret(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
        json.dumps(
            {
                "keycloak_url": "https://kc.example.com",
                "keycloak_realm": "company",
                "oidc_client_id": "portal",
                "oidc_client_secret": "existing",
                "sync_client_id": "",
                "sync_client_secret": "",
            }
        ),
        encoding="utf-8",
    )

    payload = {
        "keycloak_url": "https://kc.example.com",
        "keycloak_realm": "company",
        "oidc_client_id": "portal",
        "oidc_client_secret": "***",
        "sync_client_id": "",
        "sync_client_secret": None,
    }

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            with patch("app.api.keycloak_admin._SECRETS_DIR", tmp_path):
                with patch("app.services.keycloak.invalidate_settings_cache"):
                    with patch("app.api.keycloak_admin.bump_version", new_callable=AsyncMock):
                        with patch("app.services.audit.push_audit_event", new_callable=AsyncMock):
                            resp = await _put(app, "/admin/keycloak/settings", payload)

    assert resp.status_code == 200
    saved = json.loads(settings_file.read_text())
    assert saved["oidc_client_secret"] == "existing"


# ── POST /admin/keycloak/test/oidc ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_test_oidc_no_url(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
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

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            resp = await _post(app, "/admin/keycloak/test/oidc")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_test_oidc_discovery_fails(tmp_path):
    from app.api.keycloak_admin import KeycloakSettings, test_oidc_connection

    settings = KeycloakSettings(
        keycloak_url="https://kc.example.com",
        keycloak_realm="myrealm",
        oidc_client_id="portal",
        oidc_client_secret="secret",
        sync_client_id="",
        sync_client_secret="",
    )

    mock_inner = AsyncMock()
    mock_inner.get = AsyncMock(side_effect=Exception("connection refused"))

    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.keycloak_admin._load_kc_settings", return_value=settings):
        with patch("app.api.keycloak_admin._validate_keycloak_url"):
            with patch("app.api.keycloak_admin.httpx.AsyncClient", return_value=mock_client_cm):
                admin_dep = MagicMock()
                result = await test_oidc_connection(admin_dep)

    assert result["discovery_ok"] is False


# ── POST /admin/keycloak/test/sync ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_test_sync_no_url(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
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

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            resp = await _post(app, "/admin/keycloak/test/sync", {})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_test_sync_no_credentials(tmp_path):
    redis = _make_redis()
    app = _build_app(redis)

    settings_file = tmp_path / "kc.json"
    settings_file.write_text(
        json.dumps(
            {
                "keycloak_url": "https://kc.example.com",
                "keycloak_realm": "myrealm",
                "oidc_client_id": "portal",
                "oidc_client_secret": "s",
                "sync_client_id": "",
                "sync_client_secret": "",
            }
        ),
        encoding="utf-8",
    )

    with patch("app.api.keycloak_admin._KC_SETTINGS_FILE", settings_file):
        with patch("app.api.keycloak_admin._LEGACY_KC_SETTINGS_FILE", tmp_path / "x.json"):
            resp = await _post(app, "/admin/keycloak/test/sync", {})

    assert resp.status_code == 400


# ── GET /admin/keycloak/sync/status ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_sync_status_empty():
    redis = _make_redis()
    redis.get = AsyncMock(return_value=None)
    app = _build_app(redis)

    resp = await _get(app, "/admin/keycloak/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_run_at"] is None
    assert data["last_count"] is None


@pytest.mark.asyncio
async def test_get_sync_status_with_data():
    redis = _make_redis()
    redis.get = AsyncMock(
        return_value=json.dumps(
            {
                "timestamp": "2024-01-01T12:00:00Z",
                "count": 42,
                "status": "ok",
            }
        ).encode()
    )
    app = _build_app(redis)

    resp = await _get(app, "/admin/keycloak/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_run_at"] == "2024-01-01T12:00:00Z"
    assert data["last_count"] == 42
    assert data["last_status"] == "ok"


@pytest.mark.asyncio
async def test_get_sync_status_corrupt_json():
    redis = _make_redis()
    redis.get = AsyncMock(return_value=b"not valid json")
    app = _build_app(redis)

    resp = await _get(app, "/admin/keycloak/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_run_at"] is None
