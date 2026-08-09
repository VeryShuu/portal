"""Keycloak admin settings: OIDC client, sync service account, connection test, sync status.

Тонкий wiring-роутер (audit [M9]). Бизнес-логика вынесена в сервисы:
  * ``app.services.keycloak.admin_store`` — persistence (load/save/migrate),
    Pydantic-модели, SSRF-валидация (через ``net_guard``).
  * ``app.services.keycloak.probe`` — HTTP-пробы подключения (OIDC/sync).

SSRF-валидация — единая для всего портала: ``app.core.net_guard`` (strict для
внешнего fetch, allow-private для intranet-целей вроде Keycloak).

Обратная совместимость: имена ``_load_kc_settings``/``_save_kc_settings``/
``_to_out``/``_validate_keycloak_url``/``_KC_SETTINGS_FILE`` реэкспортятся как
делегаты к стору (существующие тесты патчат их по пути роутера).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.services.audit import make_audit_emitter
from app.services.keycloak import admin_store, probe

logger = get_logger(__name__)

_emit_audit = make_audit_emitter("keycloak_settings")

router = APIRouter(tags=["keycloak-admin"])

# ── Реэкспорт для обратной совместимости (тесты патчат по пути роутера) ─────────
# После [M9] хранилище и валидация живут в admin_store; эти алиасы сохраняют
# контракт импорта из роутера. Новые потребители должны импортировать из стору.
KeycloakSettings = admin_store.KeycloakSettings
KeycloakSettingsIn = admin_store.KeycloakSettingsIn
KeycloakSettingsOut = admin_store.KeycloakSettingsOut
_KC_SETTINGS_FILE: Path = admin_store._KC_SETTINGS_FILE
_LEGACY_KC_SETTINGS_FILE: Path = admin_store._LEGACY_KC_SETTINGS_FILE
_SECRETS_DIR: Path = admin_store._SECRETS_DIR
_SECRET_MASK: str = admin_store._SECRET_MASK


def _load_kc_settings() -> KeycloakSettings:
    return admin_store.load_settings()


def _save_kc_settings(s: KeycloakSettings) -> None:
    admin_store.save_settings(s)


def _to_out(s: KeycloakSettings) -> KeycloakSettingsOut:
    return admin_store.to_out(s)


def _validate_keycloak_url(url: str) -> None:
    admin_store.validate_keycloak_url(url)


# SyncTestIn остаётся здесь — это request-body эндпоинта, а не доменная модель.
class SyncTestIn(BaseModel):
    sync_client_id: str | None = Field(default=None)
    sync_client_secret: str | None = Field(default=None)


class SyncStatusOut(BaseModel):
    last_run_at: str | None
    last_count: int | None
    last_status: str | None


@router.get("/admin/keycloak/settings", response_model=KeycloakSettingsOut)
async def get_keycloak_settings(_: AdminDep) -> KeycloakSettingsOut:
    return _to_out(_load_kc_settings())


@router.put("/admin/keycloak/settings", response_model=KeycloakSettingsOut)
async def update_keycloak_settings(
    body: KeycloakSettingsIn,
    admin: AdminDep,
    redis: RedisDep,
) -> KeycloakSettingsOut:
    current = _load_kc_settings()

    if body.keycloak_url:
        _validate_keycloak_url(body.keycloak_url)

    # Семантика секретов: keep/clear/update (делегирована стору).
    oidc_secret = admin_store.resolve_secret(body.oidc_client_secret, current.oidc_client_secret)
    sync_secret = admin_store.resolve_secret(body.sync_client_secret, current.sync_client_secret)

    updated = KeycloakSettings(
        keycloak_url=body.keycloak_url or current.keycloak_url,
        keycloak_realm=body.keycloak_realm or current.keycloak_realm,
        oidc_client_id=body.oidc_client_id or current.oidc_client_id,
        oidc_client_secret=oidc_secret,
        sync_client_id=(
            body.sync_client_id if body.sync_client_id is not None else current.sync_client_id
        ),
        sync_client_secret=sync_secret,
    )

    _save_kc_settings(updated)

    from app.services import keycloak as kc

    kc.invalidate_settings_cache()
    await bump_version(redis, "keycloak_config")
    await bump_version(redis, "jwks")
    await _emit_audit(
        redis,
        event_type="keycloak.user_updated",
        user_id=str(admin.id),
        metadata={"sections": ["settings"]},
    )

    logger.info("admin.keycloak_settings_updated")
    return _to_out(updated)


@router.post("/admin/keycloak/test/oidc")
async def test_oidc_connection(_: AdminDep) -> dict[str, Any]:
    """Проверить OIDC-клиент: discovery + client_credentials токен (делегат probe)."""
    s = _load_kc_settings()
    probe.require_configured(s)
    _validate_keycloak_url(s.keycloak_url)
    return await probe.test_oidc_connection()


@router.post("/admin/keycloak/test/sync")
async def test_sync_connection(_: AdminDep, body: SyncTestIn | None = None) -> dict[str, Any]:
    """Проверить sync-клиент: токен + чтение 1 пользователя из Admin API (делегат probe).

    Тело опционально — позволяет проверить новые credentials до сохранения.
    """
    s = _load_kc_settings()
    probe.require_configured(s)

    sync_client_id = (
        body.sync_client_id if body and body.sync_client_id else None
    ) or s.sync_client_id
    sync_client_secret = (
        body.sync_client_secret if body and body.sync_client_secret else None
    ) or s.sync_client_secret

    if not sync_client_id or not sync_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sync Client ID и Sync Client Secret должны быть заданы",
        )
    _validate_keycloak_url(s.keycloak_url)
    return await probe.test_sync_connection(
        sync_client_id=sync_client_id,
        sync_client_secret=sync_client_secret,
    )


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
    except (ValueError, TypeError) as exc:
        # audit [H8]: diagnostic-эндпоинт статуса синка. Невалидный JSON в Redis
        # (например после смены схемы) → показываем «нет данных», но без логирования
        # это терялось. Сознательный fallback — админ видит empty status.
        logger.debug("keycloak_admin.sync_status_parse_failed", error=str(exc))
        return SyncStatusOut(last_run_at=None, last_count=None, last_status=None)
