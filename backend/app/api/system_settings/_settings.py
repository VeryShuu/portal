"""PUT / PATCH / GET handlers for ``/admin/system/settings``."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api import system_settings as _ss
from app.api.deps import AdminDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.core.sentry import scrub_sensitive
from app.core.system_config import (
    _CACHE_VERSION_KEY,
    _LOG_LEVELS,
    _SECRET_MASK,
    OnboardingStep,
    SystemSettings,
    SystemSettingsIn,
    SystemSettingsOut,
    SystemSettingsPatch,
    _save_system_settings,
    _to_out,
    apply_timezone,
    load_system_settings_shared,
)

logger = get_logger(__name__)

router = APIRouter(tags=["system-settings"])


@router.get("/admin/system/settings", response_model=SystemSettingsOut)
async def get_system_settings(_: AdminDep, redis: RedisDep) -> SystemSettingsOut:
    return _to_out(await load_system_settings_shared(redis))


async def _apply_settings(
    current: SystemSettings,
    updated: SystemSettings,
    admin,  # type: ignore[no-untyped-def]
    redis,  # type: ignore[no-untyped-def]
) -> None:
    """Persist *updated* settings and propagate side-effects.

    Common implementation shared by PUT (full update) and PATCH (partial
    update) handlers. Compares against *current* to decide which subsystems
    must be reconfigured (sentry, nginx, log level, timezone, Nextcloud
    cache), invalidates the cached settings version and writes the audit
    record describing which sections changed.
    """
    _save_system_settings(updated)
    await bump_version(redis, _CACHE_VERSION_KEY)

    if updated.sentry_dsn != current.sentry_dsn:
        import sentry_sdk

        from app.core.config import get_settings as _gs

        app_settings = _gs()
        sentry_sdk.init(
            dsn=updated.sentry_dsn,
            before_send=scrub_sensitive,  # type: ignore[arg-type]
            environment=app_settings.environment,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.05,
        )

    # Nginx configs are rendered by the nginx-config sidecar from
    # /data/settings/system.json (which _save_system_settings just wrote
    # atomically) and TLS files in /data/certs/. The sidecar inotifies
    # both paths and touches the reload trigger, so the backend no longer
    # has to regenerate or trigger a reload here.

    if updated.log_level != current.log_level:
        from app.core.logging import set_log_level

        set_log_level(updated.log_level)

    if updated.timezone != current.timezone:
        apply_timezone(updated.timezone)
        logger.info("admin.timezone_changed", timezone=updated.timezone)

    nc_changed = (
        updated.nextcloud_url != current.nextcloud_url
        or updated.nc_service_app_password != current.nc_service_app_password
        or updated.nc_service_username != current.nc_service_username
        or updated.nc_files_root != current.nc_files_root
    )
    if nc_changed:
        from app.services.nextcloud import invalidate_nc_service

        await invalidate_nc_service()

    changed_sections: list[str] = []
    if (
        updated.portal_base_url != current.portal_base_url
        or updated.allowed_cidr != current.allowed_cidr
        or updated.max_upload_size_mb != current.max_upload_size_mb
        or updated.news_attachment_max_size_mb != current.news_attachment_max_size_mb
        or updated.kb_media_max_size_mb != current.kb_media_max_size_mb
        or updated.kb_attachment_max_size_mb != current.kb_attachment_max_size_mb
        or updated.kb_trash_retention_days != current.kb_trash_retention_days
        or updated.photo_gallery_url != current.photo_gallery_url
        or updated.photo_gallery_mode != current.photo_gallery_mode
        or updated.photo_gallery_new_tab != current.photo_gallery_new_tab
        or updated.video_gallery_url != current.video_gallery_url
    ):
        changed_sections.append("system")
    if (
        updated.nextcloud_url != current.nextcloud_url
        or updated.nc_user_id_field != current.nc_user_id_field
        or updated.nc_service_app_password != current.nc_service_app_password
        or updated.nc_service_username != current.nc_service_username
        or updated.nc_files_root != current.nc_files_root
    ):
        changed_sections.append("nextcloud")
    if (
        updated.log_level != current.log_level
        or updated.log_force_json != current.log_force_json
        or updated.log_slow_request_ms != current.log_slow_request_ms
        or updated.sentry_dsn != current.sentry_dsn
        or updated.prometheus_metrics_enabled != current.prometheus_metrics_enabled
        or updated.arq_max_jobs != current.arq_max_jobs
    ):
        changed_sections.append("observability")
    if updated.timezone != current.timezone:
        changed_sections.append("timezone")

    await _ss.push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": changed_sections},
    )


_PLAIN_SETTINGS_FIELDS: tuple[str, ...] = (
    "portal_base_url",
    "nextcloud_url",
    "nc_user_id_field",
    "max_upload_size_mb",
    "allowed_cidr",
    "prometheus_metrics_enabled",
    "news_attachment_max_size_mb",
    "kb_media_max_size_mb",
    "kb_attachment_max_size_mb",
    "timezone",
    "log_force_json",
    "log_slow_request_ms",
    "arq_max_jobs",
    "photo_gallery_url",
    "photo_gallery_mode",
    "photo_gallery_new_tab",
    "video_gallery_url",
    "nc_service_username",
    "nc_files_root",
    "kb_import_max_size_mb",
    "kb_trash_retention_days",
    "phone_extract_regex",
    "onboarding_enabled",
    "onboarding_reset_trigger",
)


def _resolve_secret(body_val: str | None, current_val: str) -> str:
    """Mask-aware secret merge.

    - ``None`` (PATCH: field omitted)            → keep current
    - ``_SECRET_MASK`` (UI showed mask, no edit) → keep current
    - any other value (incl. empty string)       → replace
    """
    if body_val in (None, _SECRET_MASK):
        return current_val
    return body_val or ""


def _resolve_log_level(body_val: str | None, current_val: str) -> str:
    if body_val is None:
        return current_val
    level = body_val.upper()
    if level not in _LOG_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"log_level must be one of {_LOG_LEVELS}",
        )
    return level


def _ensure_step_ids(
    steps: list[OnboardingStep] | None,
) -> list[OnboardingStep] | None:
    """Autofill empty `id` fields with random hex tokens."""
    if steps is None:
        return None
    seen: set[str] = set()
    out: list[OnboardingStep] = []
    for s in steps:
        sid = (s.id or "").strip()
        if not sid or sid in seen:
            sid = uuid.uuid4().hex[:12]
        seen.add(sid)
        out.append(s.model_copy(update={"id": sid}))
    return out


def _build_updated_settings(
    body: SystemSettingsIn | SystemSettingsPatch,
    current: SystemSettings,
    *,
    partial: bool,
) -> SystemSettings:
    """Construct an updated :class:`SystemSettings` from request body.

    ``partial=True`` corresponds to PATCH semantics (``None`` means «keep current»);
    ``partial=False`` corresponds to PUT (every plain field is required, but the
    same fallback rule is harmless because PUT body already carries values).
    """
    kwargs: dict[str, Any] = {}
    for field in _PLAIN_SETTINGS_FIELDS:
        body_val = getattr(body, field, None)
        if partial and body_val is None:
            kwargs[field] = getattr(current, field)
        else:
            kwargs[field] = body_val
    kwargs["nc_service_app_password"] = _resolve_secret(
        body.nc_service_app_password, current.nc_service_app_password
    )
    kwargs["metrics_token"] = _resolve_secret(body.metrics_token, current.metrics_token)
    kwargs["sentry_dsn"] = _resolve_secret(body.sentry_dsn, current.sentry_dsn)
    kwargs["log_level"] = _resolve_log_level(body.log_level, current.log_level)

    if partial:
        if "onboarding_steps" in body.model_fields_set:
            kwargs["onboarding_steps"] = _ensure_step_ids(body.onboarding_steps)
        else:
            kwargs["onboarding_steps"] = current.onboarding_steps
    else:
        kwargs["onboarding_steps"] = _ensure_step_ids(
            getattr(body, "onboarding_steps", None)
        )

    return SystemSettings(**kwargs)


@router.put("/admin/system/settings", response_model=SystemSettingsOut)
async def update_system_settings(
    body: SystemSettingsIn,
    admin: AdminDep,
    redis: RedisDep,
) -> SystemSettingsOut:
    current = await load_system_settings_shared(redis)
    updated = _build_updated_settings(body, current, partial=False)
    await _apply_settings(current, updated, admin, redis)
    logger.info("admin.system_settings_updated")
    return _to_out(updated)


@router.patch("/admin/system/settings", response_model=SystemSettingsOut)
async def patch_system_settings(
    body: SystemSettingsPatch,
    admin: AdminDep,
    redis: RedisDep,
) -> SystemSettingsOut:
    """Partial update: only fields present in the request body are applied."""
    current = await load_system_settings_shared(redis)
    updated = _build_updated_settings(body, current, partial=True)
    await _apply_settings(current, updated, admin, redis)
    logger.info("admin.system_settings_patched")
    return _to_out(updated)
