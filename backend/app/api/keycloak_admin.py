"""Keycloak admin settings: OIDC client, sync service account, connection test, sync status."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(tags=["keycloak-admin"])


_BLOCKED_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback", "0.0.0.0", "169.254.169.254"}


def _is_unsafe_ip(host: str) -> bool:
    import ipaddress as _ip
    try:
        ip = _ip.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, _ip.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_keycloak_url(url: str) -> None:
    """Защита от SSRF через test endpoints.

    - Схема должна быть http/https.
    - Хост не может быть пустым, loopback или cloud-metadata (169.254.169.254).
    - Порт из диапазона 1..65535.
    Остальные приватные диапазоны разрешены (Keycloak обычно за VPN).
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL должен использовать схему http или https",
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL должен содержать имя хоста",
        )
    if host in _BLOCKED_HOSTNAMES or _is_unsafe_ip(host):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL указывает на зарезервированный адрес",
        )

_SECRETS_DIR = Path("/data/secrets")
_KC_SETTINGS_FILE = _SECRETS_DIR / "keycloak-settings.json"
# Legacy path — migrated automatically on first read.
_LEGACY_KC_SETTINGS_FILE = Path("/data/branding/keycloak-settings.json")
_SECRET_MASK = "***"


class KeycloakSettings(BaseModel):
    keycloak_url: str = Field(default="")
    keycloak_realm: str = Field(default="company")
    oidc_client_id: str = Field(default="portal")
    oidc_client_secret: str = Field(default="")
    sync_client_id: str = Field(default="")
    sync_client_secret: str = Field(default="")


class KeycloakSettingsIn(BaseModel):
    keycloak_url: str = Field(default="")
    keycloak_realm: str = Field(default="company")
    oidc_client_id: str = Field(default="portal")
    oidc_client_secret: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update",
    )
    sync_client_id: str = Field(default="")
    sync_client_secret: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; '' to clear; new value to update",
    )


class KeycloakSettingsOut(BaseModel):
    keycloak_url: str
    keycloak_realm: str
    oidc_client_id: str
    oidc_client_secret_set: bool
    sync_client_id: str
    sync_client_secret_set: bool


class SyncStatusOut(BaseModel):
    last_run_at: str | None
    last_count: int | None
    last_status: str | None


def _load_kc_settings() -> KeycloakSettings:
    # Auto-migrate from legacy /data/branding/ location to /data/secrets/.
    if not _KC_SETTINGS_FILE.exists() and _LEGACY_KC_SETTINGS_FILE.exists():
        try:
            _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
            _KC_SETTINGS_FILE.write_bytes(_LEGACY_KC_SETTINGS_FILE.read_bytes())
            try:
                os.chmod(_KC_SETTINGS_FILE, 0o600)
            except OSError:
                pass
            _LEGACY_KC_SETTINGS_FILE.unlink(missing_ok=True)
            logger.info("keycloak_admin.settings_migrated_to_secrets")
        except Exception:
            logger.exception("keycloak_admin.settings_migration_failed")

    if _KC_SETTINGS_FILE.exists():
        try:
            return KeycloakSettings.model_validate_json(_KC_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            logger.exception("keycloak_admin.settings_parse_failed")
    from app.core.config import get_settings as _gs
    s = _gs()
    return KeycloakSettings(
        keycloak_url=s.keycloak_url,
        keycloak_realm=s.keycloak_realm,
        oidc_client_id=s.keycloak_client_id,
        oidc_client_secret=s.keycloak_client_secret,
    )


def _save_kc_settings(s: KeycloakSettings) -> None:
    _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _KC_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    try:
        os.chmod(_KC_SETTINGS_FILE, 0o600)
    except OSError:
        pass


def _to_out(s: KeycloakSettings) -> KeycloakSettingsOut:
    return KeycloakSettingsOut(
        keycloak_url=s.keycloak_url,
        keycloak_realm=s.keycloak_realm,
        oidc_client_id=s.oidc_client_id,
        oidc_client_secret_set=bool(s.oidc_client_secret),
        sync_client_id=s.sync_client_id,
        sync_client_secret_set=bool(s.sync_client_secret),
    )


@router.get("/admin/keycloak/settings", response_model=KeycloakSettingsOut)
async def get_keycloak_settings(_: AdminDep) -> KeycloakSettingsOut:
    return _to_out(_load_kc_settings())


@router.put("/admin/keycloak/settings", response_model=KeycloakSettingsOut)
async def update_keycloak_settings(body: KeycloakSettingsIn, admin: AdminDep, redis: RedisDep) -> KeycloakSettingsOut:
    current = _load_kc_settings()

    if body.keycloak_url:
        _validate_keycloak_url(body.keycloak_url)

    # Semantics for both secret fields:
    #   None  → keep existing
    #   "***" → keep existing (masked sentinel from GET response)
    #   ""    → clear
    #   else  → update to new value
    def _resolve_secret(incoming: str | None, existing: str) -> str:
        if incoming is None or incoming == _SECRET_MASK:
            return existing
        return incoming

    oidc_secret = _resolve_secret(body.oidc_client_secret, current.oidc_client_secret)
    sync_secret = _resolve_secret(body.sync_client_secret, current.sync_client_secret)

    updated = KeycloakSettings(
        keycloak_url=body.keycloak_url or current.keycloak_url,
        keycloak_realm=body.keycloak_realm or current.keycloak_realm,
        oidc_client_id=body.oidc_client_id or current.oidc_client_id,
        oidc_client_secret=oidc_secret,
        sync_client_id=body.sync_client_id,
        sync_client_secret=sync_secret,
    )

    _save_kc_settings(updated)

    from app.services import keycloak as kc
    kc.invalidate_settings_cache()
    await bump_version(redis, "keycloak_config")
    await bump_version(redis, "jwks")
    await push_audit_event(
        redis,
        event_type="keycloak.user_updated",
        user_id=str(admin.id),
        resource_type="keycloak_settings",
        metadata={"sections": ["settings"]},
    )

    logger.info("admin.keycloak_settings_updated")
    return _to_out(updated)


@router.post("/admin/keycloak/test/oidc")
async def test_oidc_connection(_: AdminDep) -> dict[str, Any]:
    """Проверяет OIDC-клиент: discovery-эндпоинт + client_credentials токен."""
    s = _load_kc_settings()
    if not s.keycloak_url or not s.keycloak_realm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL и Realm должны быть заданы",
        )
    _validate_keycloak_url(s.keycloak_url)

    discovery_url = (
        f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}"
        "/.well-known/openid-configuration"
    )
    result: dict[str, Any] = {"discovery_url": discovery_url}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            data = resp.json()
            result["discovery_ok"] = True
            result["token_endpoint"] = data.get("token_endpoint")
            result["issuer"] = data.get("issuer")
    except Exception as exc:
        result["discovery_ok"] = False
        result["discovery_error"] = str(exc)
        return result

    if not s.oidc_client_id or not s.oidc_client_secret:
        result["token_ok"] = None
        result["token_note"] = "OIDC Client ID / Secret не настроены"
        return result

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                result["token_endpoint"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": s.oidc_client_id,
                    "client_secret": s.oidc_client_secret,
                },
            )
            token_resp.raise_for_status()
            result["token_ok"] = True
    except httpx.HTTPStatusError as exc:
        result["token_ok"] = False
        result["token_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        result["token_ok"] = False
        result["token_error"] = str(exc)

    return result


@router.post("/admin/keycloak/test/sync")
async def test_sync_connection(_: AdminDep) -> dict[str, Any]:
    """Проверяет sync-клиент: получает токен и пробует прочитать 1 пользователя из Admin API."""
    s = _load_kc_settings()
    if not s.keycloak_url or not s.keycloak_realm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL и Realm должны быть заданы",
        )
    if not s.sync_client_id or not s.sync_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sync Client ID и Sync Client Secret должны быть заданы",
        )
    _validate_keycloak_url(s.keycloak_url)

    token_url = (
        f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}"
        "/protocol/openid-connect/token"
    )
    result: dict[str, Any] = {}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": s.sync_client_id,
                    "client_secret": s.sync_client_secret,
                },
            )
            token_resp.raise_for_status()
            token = token_resp.json()["access_token"]
            result["token_ok"] = True
    except httpx.HTTPStatusError as exc:
        result["token_ok"] = False
        result["token_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        return result
    except Exception as exc:
        result["token_ok"] = False
        result["token_error"] = str(exc)
        return result

    admin_url = f"{s.keycloak_url.rstrip('/')}/admin/realms/{s.keycloak_realm}/users"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            users_resp = await client.get(
                admin_url,
                headers={"Authorization": f"Bearer {token}"},
                params={"first": 0, "max": 1, "briefRepresentation": "true"},
            )
            users_resp.raise_for_status()
            result["users_ok"] = True
            result["users_note"] = f"Получено {len(users_resp.json())} пользователей (тест)"
    except httpx.HTTPStatusError as exc:
        result["users_ok"] = False
        if exc.response.status_code == 403:
            result["users_error"] = (
                "403 Forbidden — убедитесь, что сервисному аккаунту назначена роль "
                "realm-management → view-users"
            )
        else:
            result["users_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        result["users_ok"] = False
        result["users_error"] = str(exc)

    return result


@router.get("/admin/keycloak/sync/status", response_model=SyncStatusOut)
async def get_sync_status(_: AdminDep, redis: RedisDep) -> SyncStatusOut:
    raw = await redis.get("kc:sync_last_run")
    if not raw:
        return SyncStatusOut(last_run_at=None, last_count=None, last_status=None)
    try:
        data = json.loads(raw)
        return SyncStatusOut(
            last_run_at=data.get("timestamp"),
            last_count=data.get("count"),
            last_status=data.get("status"),
        )
    except Exception:
        return SyncStatusOut(last_run_at=None, last_count=None, last_status=None)
