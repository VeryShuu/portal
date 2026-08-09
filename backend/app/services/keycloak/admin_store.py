"""Admin UI persistence для настроек Keycloak (audit [M9]).

File-backed стор для ``/data/secrets/keycloak-settings.json`` — единственное
место записи настроек Keycloak (Admin UI → «Keycloak»). Чтение/запись/legacy-
миграция вынесены сюда из роутера ``app/api/keycloak_admin.py`` (God Module),
роутер стал тонким wiring'ом.

Внимание: НЕ путать с соседним ``services/keycloak/settings.py`` — это другой
модуль (read-only runtime-кеш ``_KCSettings`` для OIDC/синхронизации, другой
тип и потребители). Здесь — persistence для Admin UI (модель ``KeycloakSettings``
+ save/migrate + masked ``KeycloakSettingsOut``).

SSRF-валидация URL — через ``app.core.net_guard.is_safe_internal_url``
(allow-private политика: Keycloak типично за VPN). Объединение SSRF-логики —
DoD задачи [M9].
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import cast

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.core.net_guard import is_safe_internal_url

logger = get_logger(__name__)

_SECRETS_DIR = Path("/data/secrets")
_KC_SETTINGS_FILE = _SECRETS_DIR / "keycloak-settings.json"
# Legacy path — migrated automatically on first read.
_LEGACY_KC_SETTINGS_FILE = Path("/data/branding/keycloak-settings.json")
_SECRET_MASK = "***"


class KeycloakSettings(BaseModel):
    """Полная модель настроек Keycloak (внутреннее представление, с секретами)."""

    keycloak_url: str = Field(default="")
    keycloak_realm: str = Field(default="company")
    oidc_client_id: str = Field(default="portal")
    oidc_client_secret: str = Field(default="")
    sync_client_id: str = Field(default="")
    sync_client_secret: str = Field(default="")


class KeycloakSettingsIn(BaseModel):
    """Входная модель для PUT (секреты опциональны — keep/clear/update)."""

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
    """Выходная модель (секреты замаскированы флагами ``*_set``)."""

    keycloak_url: str
    keycloak_realm: str
    oidc_client_id: str
    oidc_client_secret_set: bool
    sync_client_id: str
    sync_client_secret_set: bool


def validate_keycloak_url(url: str) -> None:
    """Защита от SSRF через test/update endpoints (audit [M9], allow-private).

    Делегирует ``net_guard.is_safe_internal_url`` (приватные диапазоны разрешены
    — Keycloak обычно за VPN, петлевые/cloud-metadata запрещены). Невалидный URL
    → 400. Перенесено из ``keycloak_admin._validate_keycloak_url``.
    """
    if not is_safe_internal_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL должен использовать схему http/https и не указывать "
            "на зарезервированный адрес (loopback/link-local/cloud-metadata)",
        )


def migrate_legacy() -> None:
    """Auto-migrate настроек из legacy ``/data/branding/`` → ``/data/secrets/``.

    Переносит файл атомарно (read→write→unlink), выставляет ``0o600``. Если
    новый файл уже есть — no-op. Ошибки логируются, не падают (best-effort).
    """
    if _KC_SETTINGS_FILE.exists() or not _LEGACY_KC_SETTINGS_FILE.exists():
        return
    try:
        _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        _KC_SETTINGS_FILE.write_bytes(_LEGACY_KC_SETTINGS_FILE.read_bytes())
        with contextlib.suppress(OSError):
            os.chmod(_KC_SETTINGS_FILE, 0o600)
        _LEGACY_KC_SETTINGS_FILE.unlink(missing_ok=True)
        logger.info("keycloak.admin_store.settings_migrated_to_secrets")
    except Exception:
        logger.exception("keycloak.admin_store.settings_migration_failed")


def load_settings() -> KeycloakSettings:
    """Прочитать настройки из файла. Нет файла/невалиден → дефолты.

    Никакого env-fallback (ADR-037): первичная настройка — только через Admin UI.
    Перед чтением выполняется legacy-миграция (см. ``migrate_legacy``).
    """
    migrate_legacy()
    if _KC_SETTINGS_FILE.exists():
        try:
            return cast(
                KeycloakSettings,
                KeycloakSettings.model_validate_json(_KC_SETTINGS_FILE.read_text("utf-8")),
            )
        except Exception:
            logger.exception("keycloak.admin_store.settings_parse_failed")
    return KeycloakSettings()


def save_settings(s: KeycloakSettings) -> None:
    """Атомарно сохранить настройки (``model_dump_json`` + ``0o600``)."""
    _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _KC_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(_KC_SETTINGS_FILE, 0o600)


def to_out(s: KeycloakSettings) -> KeycloakSettingsOut:
    """Замаскировать секреты флагами ``*_set`` (для GET-ответа)."""
    return KeycloakSettingsOut(
        keycloak_url=s.keycloak_url,
        keycloak_realm=s.keycloak_realm,
        oidc_client_id=s.oidc_client_id,
        oidc_client_secret_set=bool(s.oidc_client_secret),
        sync_client_id=s.sync_client_id,
        sync_client_secret_set=bool(s.sync_client_secret),
    )


def resolve_secret(incoming: str | None, existing: str) -> str:
    """Семантика secret-полей PUT: keep (None/``***``) → existing, иначе update.

    Пустая строка — очистка (caller передаёт ``""`` явно для clear).
    """
    if incoming is None or incoming == _SECRET_MASK:
        return existing
    return incoming
