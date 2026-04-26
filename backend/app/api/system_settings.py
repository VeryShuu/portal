from __future__ import annotations

import asyncio
import ipaddress
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import AdminDep
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["system-settings"])

_SETTINGS_DIR = Path("/data/settings")
_SYSTEM_SETTINGS_FILE = _SETTINGS_DIR / "system.json"
_NGINX_CONF_DIR = Path("/data/nginx-conf")
_NGINX_RELOAD_DIR = Path("/data/nginx")
_NGINX_RELOAD_TRIGGER = _NGINX_RELOAD_DIR / "reload-trigger"
_CERTS_DIR = Path("/data/certs")

_SECRET_MASK = "***"
_settings_cache: dict[str, Any] = {}
_CACHE_TTL = 60


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class SystemSettings(BaseModel):
    portal_base_url: str = Field(default="https://portal.company.local")
    nextcloud_url: str = Field(default="https://nextcloud.company.local")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_app_password: str = Field(default="")
    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    prometheus_metrics_enabled: bool = Field(default=True)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="Europe/Moscow")
    sentry_dsn: str = Field(default="")
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)
    arq_max_jobs: int = Field(default=10, gt=0, le=200)


class SystemSettingsIn(BaseModel):
    portal_base_url: str = Field(default="https://portal.company.local")
    nextcloud_url: str = Field(default="https://nextcloud.company.local")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_app_password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    prometheus_metrics_enabled: bool = Field(default=True)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="Europe/Moscow")
    sentry_dsn: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)
    arq_max_jobs: int = Field(default=10, gt=0, le=200)

    @field_validator("allowed_cidr")
    @classmethod
    def _validate_cidr(cls, v: str) -> str:
        for cidr in (c.strip() for c in v.split(",") if c.strip()):
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR '{cidr}': {exc}") from exc
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except Exception:
            raise ValueError(f"Unknown timezone: '{v}'. Use IANA format, e.g. 'Europe/Moscow', 'UTC'.")
        return v


class SystemSettingsOut(BaseModel):
    portal_base_url: str
    nextcloud_url: str
    nc_user_id_field: str
    nc_service_app_password_set: bool
    max_upload_size_mb: int
    allowed_cidr: str
    prometheus_metrics_enabled: bool
    news_attachment_max_size_mb: int
    kb_media_max_size_mb: int
    kb_attachment_max_size_mb: int
    log_level: str
    timezone: str
    sentry_dsn_set: bool
    log_force_json: bool | None
    log_slow_request_ms: int
    arq_max_jobs: int


class TlsStatusOut(BaseModel):
    cert_exists: bool
    key_exists: bool
    cert_expires_at: str | None
    cert_subject: str | None


def load_system_settings() -> SystemSettings:
    now = time.monotonic()
    if _settings_cache.get("data") and now - _settings_cache.get("fetched_at", 0) < _CACHE_TTL:
        return _settings_cache["data"]

    if _SYSTEM_SETTINGS_FILE.exists():
        try:
            data = SystemSettings.model_validate_json(_SYSTEM_SETTINGS_FILE.read_text("utf-8"))
            _settings_cache["data"] = data
            _settings_cache["fetched_at"] = now
            return data
        except Exception:
            pass

    from app.core.config import get_settings as _gs
    s = _gs()
    data = SystemSettings(
        portal_base_url=s.portal_base_url,
        nextcloud_url="",
        nc_user_id_field=s.nc_user_id_field,
        nc_service_app_password="",
        max_upload_size_mb=s.max_upload_size_mb,
        allowed_cidr=s.allowed_cidr,
        prometheus_metrics_enabled=s.prometheus_metrics_enabled,
        news_attachment_max_size_mb=s.news_attachment_max_size_mb,
        kb_media_max_size_mb=s.kb_media_max_size_mb,
        kb_attachment_max_size_mb=s.kb_attachment_max_size_mb,
        log_level=s.log_level,
        timezone="Europe/Moscow",
        sentry_dsn=s.sentry_dsn,
        log_force_json=s.log_force_json,
        log_slow_request_ms=s.log_slow_request_ms,
        arq_max_jobs=s.arq_max_jobs,
    )
    _settings_cache["data"] = data
    _settings_cache["fetched_at"] = now
    return data


def _save_system_settings(s: SystemSettings) -> None:
    import os as _os

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEM_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    try:
        # system.json содержит nc_service_app_password.
        _os.chmod(_SYSTEM_SETTINGS_FILE, 0o600)
    except OSError:
        pass
    _settings_cache.clear()


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
        sentry_dsn_set=bool(s.sentry_dsn),
        log_force_json=s.log_force_json,
        log_slow_request_ms=s.log_slow_request_ms,
        arq_max_jobs=s.arq_max_jobs,
    )


def apply_timezone(tz: str) -> None:
    import os as _os
    import time as _time
    _os.environ["TZ"] = tz
    try:
        _time.tzset()
    except AttributeError:
        pass


_SSL_SERVER_BLOCK = (
    "# Auto-generated by portal backend — do not edit manually\n"
    "# Regenerated when TLS certificates are uploaded/removed via Admin UI\n"
    "server {\n"
    "    listen 443 ssl;\n"
    "    http2  on;\n"
    "    server_name _;\n"
    "\n"
    "    ssl_certificate     /data/certs/portal.crt;\n"
    "    ssl_certificate_key /data/certs/portal.key;\n"
    "\n"
    "    ssl_protocols       TLSv1.2 TLSv1.3;\n"
    "    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256;\n"
    "    ssl_prefer_server_ciphers off;\n"
    "    ssl_session_cache   shared:SSL:10m;\n"
    "    ssl_session_timeout 1d;\n"
    "    ssl_session_tickets off;\n"
    "\n"
    "    if ($allowed_network = 0) {\n"
    "        return 403;\n"
    "    }\n"
    "\n"
    '    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n'
    '    add_header X-Content-Type-Options    "nosniff" always;\n'
    '    add_header X-Frame-Options           "DENY" always;\n'
    '    add_header X-XSS-Protection          "0" always;\n'
    '    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;\n'
    '    add_header Permissions-Policy        "camera=(), microphone=(), geolocation=()" always;\n'
    "    add_header Content-Security-Policy \"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'\" always;\n"
    "\n"
    '    set $backend_host  "backend:8000";\n'
    '    set $frontend_host "frontend:80";\n'
    "\n"
    "    location /media/ {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    "        proxy_set_header   X-Forwarded-Proto $scheme;\n"
    "        expires            7d;\n"
    "    }\n"
    "\n"
    "    location /api/ {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Upgrade $http_upgrade;\n"
    '        proxy_set_header   Connection "";\n'
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    "        proxy_set_header   X-Forwarded-Proto $scheme;\n"
    "        proxy_read_timeout  300s;\n"
    "        proxy_send_timeout  300s;\n"
    "    }\n"
    "\n"
    "    location ~ ^/(health|ready)$ {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "    }\n"
    "\n"
    "    location /api/v1/notifications/stream {\n"
    "        proxy_pass             http://$backend_host;\n"
    "        proxy_http_version     1.1;\n"
    '        proxy_set_header       Connection "";\n'
    "        proxy_set_header       Host $host;\n"
    "        proxy_set_header       X-Real-IP $remote_addr;\n"
    "        proxy_read_timeout     3600s;\n"
    "        proxy_buffering        off;\n"
    "        proxy_cache            off;\n"
    "        chunked_transfer_encoding on;\n"
    "    }\n"
    "\n"
    "    location /metrics {\n"
    "        proxy_pass http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header Host $host;\n"
    "    }\n"
    "\n"
    "    location /internal/kb-media/ {\n"
    "        internal;\n"
    "        alias /data/kb/media/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800, immutable";\n'
    "    }\n"
    "\n"
    "    location /internal/kb-files/ {\n"
    "        internal;\n"
    "        alias /data/kb/files/;\n"
    '        add_header Cache-Control "no-store";\n'
    "    }\n"
    "\n"
    "    location / {\n"
    "        proxy_pass         http://$frontend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "    }\n"
    "}\n"
)


def generate_ssl_server_conf() -> None:
    _NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)
    cert_path = _CERTS_DIR / "portal.crt"
    key_path = _CERTS_DIR / "portal.key"
    ssl_conf_path = _NGINX_CONF_DIR / "ssl_server.conf"

    if cert_path.exists() and key_path.exists():
        ssl_conf_path.write_text(_SSL_SERVER_BLOCK, encoding="utf-8")
        logger.info("system.ssl_server_conf_generated")
    else:
        ssl_conf_path.write_text(
            "# TLS not configured — upload cert via Admin UI -> System -> TLS\n",
            encoding="utf-8",
        )
        logger.info("system.ssl_server_conf_cleared")


def generate_nginx_confs(s: SystemSettings | None = None) -> None:
    if s is None:
        s = load_system_settings()
    _NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)

    limits_path = _NGINX_CONF_DIR / "limits.conf"
    limits_path.write_text(f"client_max_body_size {s.max_upload_size_mb}m;\n", encoding="utf-8")

    cidr_list = [c.strip() for c in s.allowed_cidr.split(",") if c.strip()]
    lines = ["geo $allowed_network {", "    default 0;"]
    for cidr in cidr_list:
        lines.append(f"    {cidr} 1;")
    lines.append("    127.0.0.1 1;")
    lines.append("}")
    (_NGINX_CONF_DIR / "allowlist.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")

    generate_ssl_server_conf()

    logger.info("system.nginx_confs_generated", max_mb=s.max_upload_size_mb, cidr_count=len(cidr_list))


def trigger_nginx_reload() -> None:
    _NGINX_RELOAD_DIR.mkdir(parents=True, exist_ok=True)
    _NGINX_RELOAD_TRIGGER.touch()
    logger.info("system.nginx_reload_triggered")


@router.get("/admin/system/settings", response_model=SystemSettingsOut)
async def get_system_settings(_: AdminDep) -> SystemSettingsOut:
    return _to_out(load_system_settings())


@router.put("/admin/system/settings", response_model=SystemSettingsOut)
async def update_system_settings(body: SystemSettingsIn, _: AdminDep) -> SystemSettingsOut:
    current = load_system_settings()

    nc_password = current.nc_service_app_password
    if body.nc_service_app_password not in (None, _SECRET_MASK):
        nc_password = body.nc_service_app_password or ""

    log_level = body.log_level.upper()
    if log_level not in _LOG_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    )
    _save_system_settings(updated)

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
    )
    if nc_changed:
        from app.services.nextcloud import invalidate_nc_service
        await invalidate_nc_service()

    logger.info("admin.system_settings_updated")
    return _to_out(updated)


@router.post("/admin/system/nginx/reload")
async def nginx_reload(_: AdminDep) -> dict[str, str]:
    generate_nginx_confs()
    trigger_nginx_reload()
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
                "openssl", "x509", "-noout", "-enddate", "-subject", "-in", str(cert_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
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


@router.post("/admin/system/tls/cert")
async def upload_tls_cert(file: UploadFile, _: AdminDep) -> dict[str, str]:
    content = await file.read()
    if not content.strip().startswith(b"-----BEGIN CERTIFICATE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат сертификата. Ожидается PEM (-----BEGIN CERTIFICATE-----)",
        )
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)
    (_CERTS_DIR / "portal.crt").write_bytes(content)
    generate_ssl_server_conf()
    trigger_nginx_reload()
    logger.info("admin.tls_cert_uploaded")
    return {"status": "ok"}


_VALID_PRIVATE_KEY_HEADERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)


@router.post("/admin/system/tls/key")
async def upload_tls_key(file: UploadFile, _: AdminDep) -> dict[str, str]:
    content = await file.read()
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
    logger.info("admin.tls_key_uploaded")
    return {"status": "ok"}


@router.delete("/admin/system/tls/cert")
async def delete_tls_cert(_: AdminDep) -> dict[str, str]:
    cert_path = _CERTS_DIR / "portal.crt"
    if cert_path.exists():
        cert_path.unlink()
    generate_ssl_server_conf()
    trigger_nginx_reload()
    return {"status": "ok"}


@router.delete("/admin/system/tls/key")
async def delete_tls_key(_: AdminDep) -> dict[str, str]:
    key_path = _CERTS_DIR / "portal.key"
    if key_path.exists():
        key_path.unlink()
    generate_ssl_server_conf()
    trigger_nginx_reload()
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
async def get_nextcloud_status(_: AdminDep) -> NcStatusOut:
    sys = load_system_settings()
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
