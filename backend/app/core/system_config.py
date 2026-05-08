from __future__ import annotations

import asyncio
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

_SECRET_MASK = "***"
_settings_cache: dict[str, Any] = {}
_settings_cache_lock = asyncio.Lock()
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
    photo_gallery_mode: str = Field(default="external")
    photo_gallery_new_tab: bool = Field(default=False)
    video_gallery_url: str = Field(default="")
    sse_max_connections_per_user: int = Field(default=10, gt=0, le=100)
    sse_max_connections_global: int = Field(default=2000, gt=0, le=10000)

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


class SystemSettingsPatch(BaseModel):
    """Partial-update schema: only provided (non-None) fields are applied."""

    portal_base_url: str | None = None
    nextcloud_url: str | None = None
    nc_user_id_field: str | None = None
    nc_service_username: str | None = None
    nc_files_root: str | None = None
    max_upload_size_mb: int | None = Field(default=None, gt=0, le=1024)
    allowed_cidr: str | None = None
    prometheus_metrics_enabled: bool | None = None
    news_attachment_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    kb_media_max_size_mb: int | None = Field(default=None, gt=0, le=512)
    kb_attachment_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    kb_import_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    log_level: str | None = None
    log_force_json: bool | None = None
    log_slow_request_ms: int | None = Field(default=None, ge=0)
    timezone: str | None = None
    arq_max_jobs: int | None = Field(default=None, gt=0, le=200)
    photo_gallery_url: str | None = None
    photo_gallery_mode: str | None = None
    photo_gallery_new_tab: bool | None = None
    video_gallery_url: str | None = None
    sse_max_connections_per_user: int | None = Field(default=None, gt=0, le=100)
    sse_max_connections_global: int | None = Field(default=None, gt=0, le=10000)
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

    @field_validator("allowed_cidr")
    @classmethod
    def _validate_cidr(cls, v: str | None) -> str | None:
        if v is None:
            return v
        for cidr in (c.strip() for c in v.split(",") if c.strip()):
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR '{cidr}': {exc}") from exc
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(v)
        except Exception as exc:
            raise ValueError(
                f"Unknown timezone: '{v}'. Use IANA format, e.g. 'Europe/Moscow', 'UTC'."
            ) from exc
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
    photo_gallery_url: str
    photo_gallery_mode: str
    photo_gallery_new_tab: bool
    video_gallery_url: str
    nc_service_username: str
    nc_files_root: str
    kb_import_max_size_mb: int
    metrics_token_set: bool


class GalleryLinksOut(BaseModel):
    photo_gallery_url: str | None
    photo_gallery_mode: str
    photo_gallery_new_tab: bool
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
        nc_user_id_field="preferred_username",
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

    async with _settings_cache_lock:
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


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically using a temp file + os.replace().

    Prevents a partial-read race where nginx (or another process) reads the
    file while it is still being written.
    """
    import os as _os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    _os.replace(tmp, path)


# Backward-compatible alias — new code should import `atomic_write`.
_atomic_write = atomic_write


def _save_system_settings(s: SystemSettings) -> None:
    import os as _os

    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(_SYSTEM_SETTINGS_FILE, s.model_dump_json(indent=2))
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
        photo_gallery_mode=s.photo_gallery_mode,
        photo_gallery_new_tab=s.photo_gallery_new_tab,
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
    try:
        _time.tzset()  # type: ignore[attr-defined]
    except AttributeError:
        logger.warning(
            "system.timezone_change_not_supported",
            tz=tz,
            reason="time.tzset() is not available on this platform (Windows?)",
        )


def invalidate_settings_cache() -> None:
    _settings_cache.clear()
