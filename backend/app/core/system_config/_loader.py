from __future__ import annotations

import time
from typing import cast

from redis.asyncio import Redis

from app.core.cache_version import get_version
from app.core.logging import get_logger

from ._schemas import SystemSettings, SystemSettingsOut

logger = get_logger(__name__)


def load_system_settings() -> SystemSettings:
    """Load runtime settings from `/data/settings/system.json`.

    Settings precedence is now JSON-only — env vars listed in `_LEGACY_ENV_MAP`
    are no longer read by the application after first start. Use
    `migrate_env_to_system_settings()` once at startup to seed the JSON file
    from legacy env vars (one-shot migration for upgrades).

    If the JSON file is absent or unparseable, default values from
    `SystemSettings` are returned.
    """
    from app.core import system_config as _root

    now = time.monotonic()
    cache = _root._settings_cache
    if cache.get("data") and now - cache.get("fetched_at", 0) < _root._CACHE_TTL:
        return cast(SystemSettings, cache["data"])

    if _root._SYSTEM_SETTINGS_FILE.exists():
        try:
            data = SystemSettings.model_validate_json(
                _root._SYSTEM_SETTINGS_FILE.read_text("utf-8")
            )
            cache["data"] = data
            cache["fetched_at"] = now
            return cast(SystemSettings, data)
        except Exception as exc:
            logger.error(
                "system_settings.parse_failed",
                path=str(_root._SYSTEM_SETTINGS_FILE),
                error=str(exc),
            )

    data = SystemSettings()
    cache["data"] = data
    cache["fetched_at"] = now
    return data


async def load_system_settings_shared(redis: Redis) -> SystemSettings:
    from app.core import system_config as _root

    current_version = await get_version(redis, _root._CACHE_VERSION_KEY)
    cache = _root._settings_cache
    if (
        cache.get("data")
        and cache.get("version") == current_version
        and time.monotonic() - cache.get("fetched_at", 0) < _root._CACHE_TTL
    ):
        return cast(SystemSettings, cache["data"])

    async with _root._settings_cache_lock:
        if (
            cache.get("data")
            and cache.get("version") == current_version
            and time.monotonic() - cache.get("fetched_at", 0) < _root._CACHE_TTL
        ):
            return cast(SystemSettings, cache["data"])

        if cache.get("version") != current_version:
            cache.clear()
        data = load_system_settings()
        cache["data"] = data
        cache["fetched_at"] = time.monotonic()
        cache["version"] = current_version
        return data


def _to_out(s: SystemSettings) -> SystemSettingsOut:
    return SystemSettingsOut(
        portal_base_url=s.portal_base_url,
        nextcloud_url=s.nextcloud_url,
        nc_user_id_field=s.nc_user_id_field,
        nc_service_app_password_set=bool(s.nc_service_app_password),
        max_upload_size_mb=s.max_upload_size_mb,
        allowed_cidr=s.allowed_cidr,
        prometheus_metrics_enabled=s.prometheus_metrics_enabled,
        news_attachment_max_size_mb=s.news_attachment_max_size_mb,
        kb_media_max_size_mb=s.kb_media_max_size_mb,
        kb_attachment_max_size_mb=s.kb_attachment_max_size_mb,
        log_level=s.log_level,
        timezone=s.timezone,
        log_force_json=s.log_force_json,
        log_slow_request_ms=s.log_slow_request_ms,
        arq_max_jobs=s.arq_max_jobs,
        photo_gallery_url=s.photo_gallery_url,
        photo_gallery_mode=s.photo_gallery_mode,
        photo_gallery_new_tab=s.photo_gallery_new_tab,
        video_gallery_url=s.video_gallery_url,
        nc_service_username=s.nc_service_username,
        nc_files_root=s.nc_files_root,
        kb_import_max_size_mb=s.kb_import_max_size_mb,
        kb_trash_retention_days=s.kb_trash_retention_days,
        metrics_token_set=bool(s.metrics_token),
        phone_extract_regex=s.phone_extract_regex,
        onboarding_enabled=s.onboarding_enabled,
        onboarding_reset_trigger=s.onboarding_reset_trigger,
        onboarding_steps=s.onboarding_steps,
    )


def apply_timezone(tz: str) -> None:
    import os as _os
    import time as _time

    _os.environ["TZ"] = tz
    try:
        _time.tzset()
    except AttributeError:
        logger.warning(
            "system.timezone_change_not_supported",
            tz=tz,
            reason="time.tzset() is not available on this platform (Windows?)",
        )
