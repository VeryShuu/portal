from __future__ import annotations

import contextlib
import ipaddress
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis

from app.core.cache_version import get_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_SETTINGS_DIR = Path("/data/settings")
_SYSTEM_SETTINGS_FILE = _SETTINGS_DIR / "system.json"
_NGINX_CONF_DIR = Path("/data/nginx-conf")
_NGINX_RELOAD_DIR = Path("/data/nginx")
_NGINX_RELOAD_TRIGGER = _NGINX_RELOAD_DIR / "reload-trigger"
_CERTS_DIR = Path("/data/certs")

_SECRET_MASK = "***"
_settings_cache: dict[str, Any] = {}
_CACHE_TTL = 60
_CACHE_VERSION_KEY = "system_settings"

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class _SystemSettingsBase(BaseModel):
    portal_base_url: str = Field(default="https://portal.company.local")
    nextcloud_url: str = Field(default="https://nextcloud.company.local")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_username: str = Field(default="portal-svc")
    nc_files_root: str = Field(default="PortalFiles")
    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    prometheus_metrics_enabled: bool = Field(default=True)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_import_max_size_mb: int = Field(default=50, gt=0, le=1024)
    log_level: str = Field(default="INFO")
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)
    timezone: str = Field(default="Europe/Moscow")
    arq_max_jobs: int = Field(default=10, gt=0, le=200)
    photo_gallery_url: str = Field(default="")
    video_gallery_url: str = Field(default="")

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
        except Exception as exc:
            raise ValueError(
                f"Unknown timezone: '{v}'. Use IANA format, e.g. 'Europe/Moscow', 'UTC'."
            ) from exc
        return v


class SystemSettings(_SystemSettingsBase):
    nc_service_app_password: str = Field(default="")
    sentry_dsn: str = Field(default="")
    metrics_token: str = Field(default="")


class SystemSettingsIn(_SystemSettingsBase):
    nc_service_app_password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    sentry_dsn: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    metrics_token: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )


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
    photo_gallery_url: str
    video_gallery_url: str
    nc_service_username: str
    nc_files_root: str
    kb_import_max_size_mb: int
    metrics_token_set: bool


class TlsStatusOut(BaseModel):
    cert_exists: bool
    key_exists: bool
    cert_expires_at: str | None
    cert_subject: str | None


class GalleryLinksOut(BaseModel):
    photo_gallery_url: str | None
    video_gallery_url: str | None


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
        except Exception as exc:
            logger.error(
                "system_settings.parse_failed",
                path=str(_SYSTEM_SETTINGS_FILE),
                error=str(exc),
            )

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
        nc_service_username=s.nc_service_username,
        nc_files_root=s.nc_files_root,
        kb_import_max_size_mb=s.kb_import_max_size_mb,
        metrics_token=s.metrics_token,
    )
    _settings_cache["data"] = data
    _settings_cache["fetched_at"] = now
    return data


async def load_system_settings_shared(redis: Redis) -> SystemSettings:
    current_version = await get_version(redis, _CACHE_VERSION_KEY)
    if (
        _settings_cache.get("data")
        and _settings_cache.get("version") == current_version
        and time.monotonic() - _settings_cache.get("fetched_at", 0) < _CACHE_TTL
    ):
        return _settings_cache["data"]

    if _settings_cache.get("version") != current_version:
        _settings_cache.clear()
    data = load_system_settings()
    _settings_cache["data"] = data
    _settings_cache["fetched_at"] = time.monotonic()
    _settings_cache["version"] = current_version
    return data


def _save_system_settings(s: SystemSettings) -> None:
    import os as _os

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEM_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        _os.chmod(_SYSTEM_SETTINGS_FILE, 0o600)
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
        photo_gallery_url=s.photo_gallery_url,
        video_gallery_url=s.video_gallery_url,
        nc_service_username=s.nc_service_username,
        nc_files_root=s.nc_files_root,
        kb_import_max_size_mb=s.kb_import_max_size_mb,
        metrics_token_set=bool(s.metrics_token),
    )


def apply_timezone(tz: str) -> None:
    import os as _os
    import time as _time

    _os.environ["TZ"] = tz
    with contextlib.suppress(AttributeError):
        _time.tzset()  # type: ignore[attr-defined]


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
    "    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256;\n"  # noqa: E501
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
    "    add_header Content-Security-Policy \"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'\" always;\n"  # noqa: E501
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

    logger.info(
        "system.nginx_confs_generated",
        max_mb=s.max_upload_size_mb,
        cidr_count=len(cidr_list),
    )


def trigger_nginx_reload() -> None:
    _NGINX_RELOAD_DIR.mkdir(parents=True, exist_ok=True)
    _NGINX_RELOAD_TRIGGER.touch()
    logger.info("system.nginx_reload_triggered")


_VALID_PRIVATE_KEY_HEADERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)


def invalidate_settings_cache() -> None:
    _settings_cache.clear()
