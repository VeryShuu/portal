from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import AdminDep, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.core.sentry import scrub_sensitive
from app.core.system_config import (
    _CACHE_VERSION_KEY,
    _CERTS_DIR,
    _LOG_LEVELS,
    _SECRET_MASK,
    _VALID_PRIVATE_KEY_HEADERS,
    GalleryLinksOut,
    SystemSettings,
    SystemSettingsIn,
    SystemSettingsOut,
    SystemSettingsPatch,
    TlsStatusOut,
    _save_system_settings,
    _to_out,
    apply_timezone,
    generate_nginx_confs,
    generate_ssl_server_conf,
    load_system_settings_shared,
    trigger_nginx_reload,
)
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(tags=["system-settings"])


@router.get("/admin/system/settings", response_model=SystemSettingsOut)
async def get_system_settings(_: AdminDep, redis: RedisDep) -> SystemSettingsOut:
    return _to_out(await load_system_settings_shared(redis))


@router.put("/admin/system/settings", response_model=SystemSettingsOut)
async def update_system_settings(
    body: SystemSettingsIn,
    admin: AdminDep,
    redis: RedisDep,
) -> SystemSettingsOut:
    current = await load_system_settings_shared(redis)

    nc_password = current.nc_service_app_password
    if body.nc_service_app_password not in (None, _SECRET_MASK):
        nc_password = body.nc_service_app_password or ""

    metrics_token = current.metrics_token
    if body.metrics_token not in (None, _SECRET_MASK):
        metrics_token = body.metrics_token or ""

    log_level = body.log_level.upper()
    if log_level not in _LOG_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"log_level must be one of {_LOG_LEVELS}",
        )

    sentry_dsn = current.sentry_dsn
    if body.sentry_dsn not in (None, _SECRET_MASK):
        sentry_dsn = body.sentry_dsn or ""

    updated = SystemSettings(
        portal_base_url=body.portal_base_url,
        nextcloud_url=body.nextcloud_url,
        nc_user_id_field=body.nc_user_id_field,
        nc_service_app_password=nc_password,
        max_upload_size_mb=body.max_upload_size_mb,
        allowed_cidr=body.allowed_cidr,
        prometheus_metrics_enabled=body.prometheus_metrics_enabled,
        news_attachment_max_size_mb=body.news_attachment_max_size_mb,
        kb_media_max_size_mb=body.kb_media_max_size_mb,
        kb_attachment_max_size_mb=body.kb_attachment_max_size_mb,
        log_level=log_level,
        timezone=body.timezone,
        sentry_dsn=sentry_dsn,
        log_force_json=body.log_force_json,
        log_slow_request_ms=body.log_slow_request_ms,
        arq_max_jobs=body.arq_max_jobs,
        photo_gallery_url=body.photo_gallery_url,
        photo_gallery_mode=body.photo_gallery_mode,
        photo_gallery_new_tab=body.photo_gallery_new_tab,
        video_gallery_url=body.video_gallery_url,
        nc_service_username=body.nc_service_username,
        nc_files_root=body.nc_files_root,
        kb_import_max_size_mb=body.kb_import_max_size_mb,
        metrics_token=metrics_token,
    )
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

    nginx_changed = (
        updated.max_upload_size_mb != current.max_upload_size_mb
        or updated.allowed_cidr != current.allowed_cidr
    )
    if nginx_changed:
        generate_nginx_confs(updated)
        trigger_nginx_reload()

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

    nc_password = current.nc_service_app_password
    if body.nc_service_app_password not in (None, _SECRET_MASK):
        nc_password = body.nc_service_app_password or ""

    metrics_token = current.metrics_token
    if body.metrics_token not in (None, _SECRET_MASK):
        metrics_token = body.metrics_token or ""

    sentry_dsn = current.sentry_dsn
    if body.sentry_dsn not in (None, _SECRET_MASK):
        sentry_dsn = body.sentry_dsn or ""

    log_level = current.log_level
    if body.log_level is not None:
        log_level = body.log_level.upper()
        if log_level not in _LOG_LEVELS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"log_level must be one of {_LOG_LEVELS}",
            )

    def _pick(body_val, current_val):
        return body_val if body_val is not None else current_val

    updated = SystemSettings(
        portal_base_url=_pick(body.portal_base_url, current.portal_base_url),
        nextcloud_url=_pick(body.nextcloud_url, current.nextcloud_url),
        nc_user_id_field=_pick(body.nc_user_id_field, current.nc_user_id_field),
        nc_service_app_password=nc_password,
        max_upload_size_mb=_pick(body.max_upload_size_mb, current.max_upload_size_mb),
        allowed_cidr=_pick(body.allowed_cidr, current.allowed_cidr),
        prometheus_metrics_enabled=_pick(
            body.prometheus_metrics_enabled, current.prometheus_metrics_enabled
        ),
        news_attachment_max_size_mb=_pick(
            body.news_attachment_max_size_mb, current.news_attachment_max_size_mb
        ),
        kb_media_max_size_mb=_pick(body.kb_media_max_size_mb, current.kb_media_max_size_mb),
        kb_attachment_max_size_mb=_pick(
            body.kb_attachment_max_size_mb, current.kb_attachment_max_size_mb
        ),
        log_level=log_level,
        timezone=_pick(body.timezone, current.timezone),
        sentry_dsn=sentry_dsn,
        log_force_json=_pick(body.log_force_json, current.log_force_json),
        log_slow_request_ms=_pick(body.log_slow_request_ms, current.log_slow_request_ms),
        arq_max_jobs=_pick(body.arq_max_jobs, current.arq_max_jobs),
        photo_gallery_url=_pick(body.photo_gallery_url, current.photo_gallery_url),
        photo_gallery_mode=_pick(body.photo_gallery_mode, current.photo_gallery_mode),
        photo_gallery_new_tab=_pick(body.photo_gallery_new_tab, current.photo_gallery_new_tab),
        video_gallery_url=_pick(body.video_gallery_url, current.video_gallery_url),
        nc_service_username=_pick(body.nc_service_username, current.nc_service_username),
        nc_files_root=_pick(body.nc_files_root, current.nc_files_root),
        kb_import_max_size_mb=_pick(body.kb_import_max_size_mb, current.kb_import_max_size_mb),
        metrics_token=metrics_token,
    )
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

    nginx_changed = (
        updated.max_upload_size_mb != current.max_upload_size_mb
        or updated.allowed_cidr != current.allowed_cidr
    )
    if nginx_changed:
        generate_nginx_confs(updated)
        trigger_nginx_reload()

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


@router.post("/admin/system/nginx/reload")
async def nginx_reload(admin: AdminDep, redis: RedisDep) -> dict[str, str]:
    generate_nginx_confs()
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
    cert_path = _CERTS_DIR / "portal.crt"
    key_path = _CERTS_DIR / "portal.key"

    cert_expires_at = None
    cert_subject = None

    if cert_path.exists():
        try:
            proc = await asyncio.create_subprocess_exec(
                "openssl",
                "x509",
                "-noout",
                "-enddate",
                "-subject",
                "-in",
                str(cert_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)  # type: ignore[arg-type]
            for line in stdout.decode().splitlines():
                if line.startswith("notAfter="):
                    cert_expires_at = line.removeprefix("notAfter=").strip()
                elif line.startswith("subject="):
                    cert_subject = line.removeprefix("subject=").strip()
        except Exception:
            pass

    return TlsStatusOut(
        cert_exists=cert_path.exists(),
        key_exists=key_path.exists(),
        cert_expires_at=cert_expires_at,
        cert_subject=cert_subject,
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
    if not content.strip().startswith(b"-----BEGIN CERTIFICATE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат сертификата. Ожидается PEM (-----BEGIN CERTIFICATE-----)",
        )
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)
    (_CERTS_DIR / "portal.crt").write_bytes(content)
    generate_ssl_server_conf()
    trigger_nginx_reload()
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
    generate_ssl_server_conf()
    trigger_nginx_reload()
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
    generate_ssl_server_conf()
    trigger_nginx_reload()
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
    generate_ssl_server_conf()
    trigger_nginx_reload()
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
