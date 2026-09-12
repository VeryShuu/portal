"""Keycloak settings: file-backed, cached in-memory, with Redis version key."""

from __future__ import annotations

import time
from typing import cast

from redis.asyncio import Redis

from app.core.cache_version import get_version
from app.core.config import get_settings
from app.core.logging import get_logger

from . import _state

logger = get_logger(__name__)
_app_settings = get_settings()


class _KCSettings:
    __slots__ = (
        "keycloak_realm",
        "keycloak_url",
        "oidc_client_id",
        "oidc_client_secret",
        "sync_client_id",
        "sync_client_secret",
    )

    def __init__(
        self,
        keycloak_url: str,
        keycloak_realm: str,
        oidc_client_id: str,
        oidc_client_secret: str,
        sync_client_id: str = "",
        sync_client_secret: str = "",
    ) -> None:
        self.keycloak_url = keycloak_url.rstrip("/")
        self.keycloak_realm = keycloak_realm
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.sync_client_id = sync_client_id
        self.sync_client_secret = sync_client_secret


def _get_kc_settings() -> _KCSettings:
    """Load Keycloak settings from ``/data/secrets/keycloak-settings.json``.

    Single source of truth — управляется через Admin UI (``KeycloakTab``).
    Если файла нет / он невалиден — возвращаются пустые значения; вызывающий код
    должен реагировать (например, OIDC-флоу падает с 503). Никакого fallback на
    переменные окружения больше нет (см. ADR-037).

    In-memory cached 60 s.
    """
    # Lazy lookup via package namespace so tests can patch _KC_SETTINGS_FILE.
    from app.services import keycloak as _kc

    now = time.monotonic()
    if (
        _state._settings_cache.get("data")
        and now - _state._settings_cache.get("fetched_at", 0) < _state._SETTINGS_CACHE_TTL
    ):
        return cast(_KCSettings, _state._settings_cache["data"])

    kc_file = (
        _kc._KC_SETTINGS_FILE if _kc._KC_SETTINGS_FILE.exists() else _kc._LEGACY_KC_SETTINGS_FILE
    )
    if kc_file.exists():
        try:
            import json

            raw = json.loads(kc_file.read_text("utf-8"))
            kc_url = raw.get("keycloak_url", "")
            kc_realm = raw.get("keycloak_realm", "")
            if kc_url and kc_realm:
                data = _KCSettings(
                    keycloak_url=kc_url,
                    keycloak_realm=kc_realm,
                    oidc_client_id=raw.get("oidc_client_id") or "",
                    oidc_client_secret=raw.get("oidc_client_secret") or "",
                    sync_client_id=raw.get("sync_client_id", ""),
                    sync_client_secret=raw.get("sync_client_secret", ""),
                )
                _state._settings_cache["data"] = data
                _state._settings_cache["fetched_at"] = now
                return data
        except Exception as exc:
            logger.debug("keycloak.settings_load_failed", error=str(exc))

    data = _KCSettings(
        keycloak_url="",
        keycloak_realm="",
        oidc_client_id="",
        oidc_client_secret="",
    )
    _state._settings_cache["data"] = data
    _state._settings_cache["fetched_at"] = now
    return data


async def _get_kc_settings_async(redis: Redis | None = None) -> _KCSettings:
    from app.services import keycloak as _kc

    _owned = redis is None
    if _owned:
        redis = Redis.from_url(_app_settings.redis_url, decode_responses=True)
    assert redis is not None
    try:
        current_version = await _kc.get_version(redis, _state._SETTINGS_VERSION_KEY)
    finally:
        if _owned:
            await redis.aclose()

    now = time.monotonic()
    if (
        _state._settings_cache.get("data")
        and _state._settings_cache.get("version") == current_version
        and now - _state._settings_cache.get("fetched_at", 0) < _state._SETTINGS_CACHE_TTL
    ):
        return cast(_KCSettings, _state._settings_cache["data"])

    if _state._settings_cache.get("version") != current_version:
        _state._settings_cache.clear()
    data = _kc._get_kc_settings()
    _state._settings_cache["version"] = current_version
    _state._settings_cache["fetched_at"] = now
    _state._settings_cache["data"] = data
    return data


def invalidate_settings_cache() -> None:
    """Public API: drop cached Keycloak settings. Used by admin handlers after save."""
    _state._settings_cache.clear()


def get_kc_settings() -> _KCSettings:
    """Public wrapper — returns current Keycloak settings (file-backed, 60 s cache)."""
    from app.services import keycloak as _kc

    return cast(_KCSettings, _kc._get_kc_settings())


# Re-export for type-checking consumers
__all__ = [
    "_KCSettings",
    "_get_kc_settings",
    "_get_kc_settings_async",
    "get_kc_settings",
    "get_version",
    "invalidate_settings_cache",
]
