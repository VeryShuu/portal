from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

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
        nextcloud_url=s.nextcloud_url,
        nc_user_id_field=s.nc_user_id_field,
        nc_service_app_password=s.nc_service_app_password,
        max_upload_size_mb=s.max_upload_size_mb,
        allowed_cidr=s.allowed_cidr,
        prometheus_metrics_enabled=s.prometheus_metrics_enabled,
        news_attachment_max_size_mb=s.news_attachment_max_size_mb,
        kb_media_max_size_mb=s.kb_media_max_size_mb,
        kb_attachment_max_size_mb=s.kb_attachment_max_size_mb,
        log_level=s.log_level,
    )
    _settings_cache["data"] = data
    _settings_cache["fetched_at"] = now
    return data


def _save_system_settings(s: SystemSettings) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEM_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
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
    )


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
            result = subprocess.run(
                ["openssl", "x509", "-noout", "-enddate", "-subject", "-in", str(cert_path)],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
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
    trigger_nginx_reload()
    logger.info("admin.tls_cert_uploaded")
    return {"status": "ok"}


@router.post("/admin/system/tls/key")
async def upload_tls_key(file: UploadFile, _: AdminDep) -> dict[str, str]:
    content = await file.read()
    if not content.strip().startswith(b"-----BEGIN"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат ключа. Ожидается PEM (-----BEGIN ... PRIVATE KEY-----)",
        )
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)
    (_CERTS_DIR / "portal.key").write_bytes(content)
    trigger_nginx_reload()
    logger.info("admin.tls_key_uploaded")
    return {"status": "ok"}


@router.delete("/admin/system/tls/cert")
async def delete_tls_cert(_: AdminDep) -> dict[str, str]:
    cert_path = _CERTS_DIR / "portal.crt"
    if cert_path.exists():
        cert_path.unlink()
        trigger_nginx_reload()
    return {"status": "ok"}


@router.delete("/admin/system/tls/key")
async def delete_tls_key(_: AdminDep) -> dict[str, str]:
    key_path = _CERTS_DIR / "portal.key"
    if key_path.exists():
        key_path.unlink()
        trigger_nginx_reload()
    return {"status": "ok"}
