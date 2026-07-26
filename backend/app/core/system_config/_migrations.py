from __future__ import annotations

import os as _os
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
    "LOG_LEVEL": "log_level",
    "LOG_FORCE_JSON": "log_force_json",
    "LOG_SLOW_REQUEST_MS": "log_slow_request_ms",
    "ARQ_MAX_JOBS": "arq_max_jobs",
    "NC_FILES_ROOT": "nc_files_root",
    "NC_SERVICE_USERNAME": "nc_service_username",
}


def _collect_legacy_env() -> dict[str, str]:
    """Return ``{ENV_VAR: raw_value}`` for every legacy env var currently set.

    Empty/None values are treated as unset.
    """
    return {
        env_key: _os.environ[env_key]
        for env_key in _LEGACY_ENV_MAP
        if _os.environ.get(env_key) not in (None, "")
    }


def _log_deprecated_if_present(present_legacy: dict[str, str]) -> None:
    """Warn the operator that legacy env vars are being ignored.

    Called when `system.json` already exists but legacy env vars still linger
    in the environment — they're no longer read at runtime, so the operator
    should remove them from `.env`.
    """
    if not present_legacy:
        return
    logger.warning(
        "config.deprecated_env_vars_ignored",
        vars=sorted(present_legacy.keys()),
        note=(
            "These env vars are deprecated — runtime settings are now "
            "stored in /data/settings/system.json. Manage them via the "
            "Admin UI and remove them from .env."
        ),
    )


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

    Concurrency: the read-modify-write is serialized through a kernel-level
    `flock` on `<settings_dir>/.migration.lock` (see `_migration_lock`). This
    handles the `docker compose up` race where backend, worker and migrations
    start in parallel and would otherwise all write `system.json`. The file
    existence check is re-run *inside* the lock so a process that waited while
    a peer migrated observes the freshly-created file and returns False.

    Fast path: when no legacy env vars are present AND the settings file
    doesn't exist, we return False *without touching the filesystem* — no
    lock acquisition, no `mkdir`. This keeps `import app.main` side-effect-free
    on CI/test runners where `/data` is absent or read-only (openapi-export
    job, unit tests, ad-hoc `uvicorn` launches).
    """
    from app.core import system_config as _root

    settings_file = _root._SYSTEM_SETTINGS_FILE
    settings_dir = settings_file.parent

    # Fast path (no FS writes, no lock): the common case on CI/test/dev where
    # no legacy env vars are set. We must NOT touch the filesystem here —
    # `settings_dir` resolves to `/data/settings`, which doesn't exist and
    # isn't writable outside the container (e.g. openapi-export job, unit
    # tests, `uvicorn app.main:app` on a CI runner). Creating it eagerly would
    # raise PermissionError and crash any process that imports `app.main`.
    present_legacy = _collect_legacy_env()
    # No legacy env AND no existing settings file → nothing to migrate and
    # nothing to warn about; bail out without any I/O (no mkdir, no lock).
    if not present_legacy and not settings_file.exists():
        return False

    from app.core.system_config._migration_lock import migration_lock

    with migration_lock(settings_dir):
        # Re-check inside the lock — another process may have migrated
        # while we were waiting. Both the legacy-env snapshot AND the
        # file-existence check must be re-read here to avoid a stale view.
        present_legacy = _collect_legacy_env()

        if settings_file.exists():
            _log_deprecated_if_present(present_legacy)
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
                path=str(settings_file),
            )
            return False

        logger.info(
            "config.env_migrated_to_json",
            vars=sorted(present_legacy.keys()),
            path=str(settings_file),
            note="Legacy env vars copied to system.json; remove them from .env on next deploy.",
        )
        return True
