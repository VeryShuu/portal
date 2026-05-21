from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.core.sentry import scrub_sensitive
from app.core.system_config import (
    _CACHE_VERSION_KEY,
    _LOG_LEVELS,
    _SECRET_MASK,
    GalleryLinksOut,
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
from app.services.audit import push_audit_event
from app.services.nginx_config import (
    _CERTS_DIR,
    trigger_nginx_reload,
)
from app.services.tls_status import TlsStatusOut, get_tls_status_info

logger = get_logger(__name__)


class StaffSettingsOut(BaseModel):
    phone_extract_regex: str


class OnboardingPublicOut(BaseModel):
    onboarding_enabled: bool
    onboarding_reset_trigger: str
    onboarding_steps: list[OnboardingStep] | None = None


class OnboardingResetOut(BaseModel):
    updated: int
    reset_trigger: str


class OnboardingStepResetViewsIn(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)


class OnboardingStepResetViewsOut(BaseModel):
    updated: int
    step_id: str


router = APIRouter(tags=["system-settings"])

_VALID_PRIVATE_KEY_HEADERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)


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

    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": changed_sections},
    )


# Plain (non-secret, non-validated) fields shared between PUT and PATCH.
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


@router.get("/portal/gallery-links", response_model=GalleryLinksOut)
async def get_gallery_links(redis: RedisDep) -> GalleryLinksOut:
    s = await load_system_settings_shared(redis)
    return GalleryLinksOut(
        photo_gallery_url=s.photo_gallery_url or None,
        photo_gallery_mode=s.photo_gallery_mode,
        photo_gallery_new_tab=s.photo_gallery_new_tab,
        video_gallery_url=s.video_gallery_url or None,
    )


@router.get("/portal/staff-settings", response_model=StaffSettingsOut)
async def get_staff_settings(redis: RedisDep) -> StaffSettingsOut:
    s = await load_system_settings_shared(redis)
    return StaffSettingsOut(phone_extract_regex=s.phone_extract_regex)


@router.get("/portal/onboarding", response_model=OnboardingPublicOut)
async def get_onboarding_public(redis: RedisDep) -> OnboardingPublicOut:
    s = await load_system_settings_shared(redis)
    return OnboardingPublicOut(
        onboarding_enabled=s.onboarding_enabled,
        onboarding_reset_trigger=s.onboarding_reset_trigger,
        onboarding_steps=s.onboarding_steps,
    )


@router.post(
    "/admin/system/settings/onboarding/reset",
    response_model=OnboardingResetOut,
)
async def reset_onboarding(
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> OnboardingResetOut:
    current = await load_system_settings_shared(redis)
    result = await db.execute(
        sa_text(
            "UPDATE users "
            "SET preferences = preferences - 'onboarding_completed' "
            "WHERE preferences ? 'onboarding_completed'"
        )
    )
    await db.commit()
    updated = int(result.rowcount or 0)

    reset_trigger = datetime.now(timezone.utc).isoformat()
    new_settings = current.model_copy(update={"onboarding_reset_trigger": reset_trigger})
    _save_system_settings(new_settings)
    await bump_version(redis, _CACHE_VERSION_KEY)

    await push_audit_event(
        redis,
        event_type="system_settings.onboarding_reset",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"updated_users": updated, "reset_trigger": reset_trigger},
    )
    logger.info(
        "admin.onboarding_reset",
        admin_id=str(admin.id),
        updated_users=updated,
        reset_trigger=reset_trigger,
    )
    return OnboardingResetOut(updated=updated, reset_trigger=reset_trigger)


@router.post(
    "/admin/system/settings/onboarding/steps/reset-views",
    response_model=OnboardingStepResetViewsOut,
)
async def reset_onboarding_step_views(
    body: OnboardingStepResetViewsIn,
    admin: AdminDep,
    redis: RedisDep,
    db: DbDep,
) -> OnboardingStepResetViewsOut:
    """Remove the given step_id from every user's onboarding_seen_step_ids array."""
    result = await db.execute(
        sa_text(
            "UPDATE users "
            "SET preferences = jsonb_set("
            "    preferences, "
            "    '{onboarding_seen_step_ids}', "
            "    (preferences->'onboarding_seen_step_ids') - :sid"
            ") "
            "WHERE jsonb_typeof(preferences->'onboarding_seen_step_ids') = 'array' "
            "  AND preferences->'onboarding_seen_step_ids' ? :sid"
        ),
        {"sid": body.step_id},
    )
    await db.commit()
    updated = int(result.rowcount or 0)

    await push_audit_event(
        redis,
        event_type="system_settings.onboarding_step_reset_views",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={
            "step_id": body.step_id,
            "updated_users": updated,
        },
    )
    logger.info(
        "admin.onboarding_step_reset_views",
        admin_id=str(admin.id),
        step_id=body.step_id,
        updated_users=updated,
    )
    return OnboardingStepResetViewsOut(updated=updated, step_id=body.step_id)


@router.post("/admin/system/nginx/reload")
async def nginx_reload(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    # The nginx-config sidecar already keeps the rendered configs in sync
    # with system.json / certs via inotify; this endpoint just forces an
    # immediate nginx reload without waiting for the next sidecar cycle.
    trigger_nginx_reload()
    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["nginx"]},
    )
    return {"status": "reload_triggered"}


@router.get("/admin/system/tls/status", response_model=TlsStatusOut)
async def get_tls_status(_: AdminDep) -> TlsStatusOut:
    return await get_tls_status_info(
        cert_path=_CERTS_DIR / "portal.crt",
        key_path=_CERTS_DIR / "portal.key",
    )


_TLS_FILE_MAX_BYTES = 64 * 1024  # 64 KiB is sufficient for any PEM cert/key


@router.post("/admin/system/tls/cert")
async def upload_tls_cert(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    content = await file.read(_TLS_FILE_MAX_BYTES + 1)
    if len(content) > _TLS_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл сертификата слишком большой (максимум 64 KiB)",
        )
    if not content.strip().startswith(b"-----BEGIN CERTIFICATE-----"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат сертификата. Ожидается PEM (-----BEGIN CERTIFICATE-----)",
        )
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)
    (_CERTS_DIR / "portal.crt").write_bytes(content)
    # nginx-config sidecar inotifies /data/certs/, re-renders ssl_server.conf
    # (HTTP→HTTPS variant once both crt+key are present) and touches the
    # nginx reload trigger automatically.
    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    logger.info("admin.tls_cert_uploaded")
    return {"status": "ok"}


@router.post("/admin/system/tls/key")
async def upload_tls_key(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    content = await file.read(_TLS_FILE_MAX_BYTES + 1)
    if len(content) > _TLS_FILE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл ключа слишком большой (максимум 64 KiB)",
        )
    head = content.strip()
    if not any(head.startswith(h) for h in _VALID_PRIVATE_KEY_HEADERS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Неверный формат ключа. Ожидается PEM-файл приватного ключа "
                "(-----BEGIN PRIVATE KEY-----, -----BEGIN RSA PRIVATE KEY----- и т.п.). "
                "Сертификаты и CSR сюда загружать нельзя."
            ),
        )
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)
    key_path = _CERTS_DIR / "portal.key"
    key_path.write_bytes(content)
    try:
        import os as _os

        _os.chmod(key_path, 0o600)
    except OSError:
        pass
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    logger.info("admin.tls_key_uploaded")
    return {"status": "ok"}


@router.delete("/admin/system/tls/cert")
async def delete_tls_cert(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    cert_path = _CERTS_DIR / "portal.crt"
    if cert_path.exists():
        cert_path.unlink()
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    return {"status": "ok"}


@router.delete("/admin/system/tls/key")
async def delete_tls_key(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    key_path = _CERTS_DIR / "portal.key"
    if key_path.exists():
        key_path.unlink()
    # nginx-config sidecar inotifies /data/certs/ and re-renders+reloads.
    await push_audit_event(
        redis,
        event_type="system_settings.updated",
        user_id=str(admin.id),
        resource_type="system_settings",
        metadata={"sections": ["tls"]},
    )
    return {"status": "ok"}


class NcStatusOut(BaseModel):
    ok: bool
    configured: bool
    server_reachable: bool
    nc_version: str | None
    auth_ok: bool
    webdav_ok: bool
    details: str | None


@router.get("/admin/system/nextcloud/status", response_model=NcStatusOut)
async def get_nextcloud_status(_: AdminDep, redis: RedisDep) -> NcStatusOut:
    sys = await load_system_settings_shared(redis)
    if not sys.nextcloud_url or not sys.nc_service_app_password:
        return NcStatusOut(
            ok=False,
            configured=False,
            server_reachable=False,
            nc_version=None,
            auth_ok=False,
            webdav_ok=False,
            details="URL или пароль сервисного аккаунта не заданы",
        )
    from app.services.nextcloud import get_nc_service

    svc = get_nc_service()
    result = await svc.detailed_health_check()
    return NcStatusOut(**result)
