from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

from ._schemas import SystemSettings

logger = get_logger(__name__)


# Legacy env vars that were previously read by `Settings` and overlapped with
# `SystemSettings`. The mapping is consulted by `migrate_env_to_system_settings()`
# during one-shot upgrade migration. Order is irrelevant — Pydantic validates types.
_LEGACY_ENV_MAP: dict[str, str] = {
    "PORTAL_BASE_URL": "portal_base_url",
    "MAX_UPLOAD_SIZE_MB": "max_upload_size_mb",
    "NEWS_ATTACHMENT_MAX_SIZE_MB": "news_attachment_max_size_mb",
    "KB_MEDIA_MAX_SIZE_MB": "kb_media_max_size_mb",
    "KB_ATTACHMENT_MAX_SIZE_MB": "kb_attachment_max_size_mb",
    "KB_IMPORT_MAX_SIZE_MB": "kb_import_max_size_mb",
    "ALLOWED_CIDR": "allowed_cidr",
    "PROMETHEUS_METRICS_ENABLED": "prometheus_metrics_enabled",
    "METRICS_TOKEN": "metrics_token",
    "SENTRY_DSN": "sentry_dsn",
    "LOG_LEVEL": "log_level",
    "LOG_FORCE_JSON": "log_force_json",
    "LOG_SLOW_REQUEST_MS": "log_slow_request_ms",
    "ARQ_MAX_JOBS": "arq_max_jobs",
    "NC_FILES_ROOT": "nc_files_root",
    "NC_SERVICE_USERNAME": "nc_service_username",
}


def migrate_env_to_system_settings() -> bool:
    """One-shot migration from legacy env vars to `system.json`.

    Behaviour:
    - If `/data/settings/system.json` is absent and any legacy env var is set,
      build a `SystemSettings` instance from defaults overlaid with env values
      and persist it. Returns True.
    - If `system.json` already exists, do not touch it. If legacy env vars are
      still present in the environment, log a warning so the operator removes
      them from `.env` (single source of truth).
    - Returns False when no migration was performed.

    Safe to call multiple times — idempotent after first successful migration.
    Must be called BEFORE the first `load_system_settings()` for the migrated
    values to take effect on this process start.
    """
    import os as _os

    from app.core import system_config as _root

    present_legacy = {
        env_key: _os.environ[env_key]
        for env_key in _LEGACY_ENV_MAP
        if _os.environ.get(env_key) not in (None, "")
    }

    if _root._SYSTEM_SETTINGS_FILE.exists():
        if present_legacy:
            logger.warning(
                "config.deprecated_env_vars_ignored",
                vars=sorted(present_legacy.keys()),
                note=(
                    "These env vars are deprecated — runtime settings are now "
                    "stored in /data/settings/system.json. Manage them via the "
                    "Admin UI and remove them from .env."
                ),
            )
        return False

    if not present_legacy:
        return False

    kwargs: dict[str, Any] = {}
    for env_key, raw_value in present_legacy.items():
        field = _LEGACY_ENV_MAP[env_key]
        kwargs[field] = raw_value

    try:
        data = SystemSettings(**kwargs)
    except Exception as exc:
        logger.error(
            "config.env_migration_failed",
            error=str(exc),
            vars=sorted(present_legacy.keys()),
        )
        return False

    try:
        _root._save_system_settings(data)
    except Exception as exc:
        logger.error(
            "config.env_migration_persist_failed",
            error=str(exc),
            path=str(_root._SYSTEM_SETTINGS_FILE),
        )
        return False

    logger.info(
        "config.env_migrated_to_json",
        vars=sorted(present_legacy.keys()),
        path=str(_root._SYSTEM_SETTINGS_FILE),
        note="Legacy env vars copied to system.json; remove them from .env on next deploy.",
    )
    return True
