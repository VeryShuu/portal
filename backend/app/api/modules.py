import contextlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.api.deps import AdminDep, CurrentUser, RedisDep
from app.core.cache_version import bump_version, get_version
from app.core.logging import get_logger
from app.services.audit import push_audit_event

logger = get_logger(__name__)
router = APIRouter(tags=["modules"])

_SETTINGS_DIR = Path("/data/settings")
_MODULES_FILE = _SETTINGS_DIR / "modules.json"

_modules_cache: dict[str, Any] = {}
_CACHE_TTL = 60
_CACHE_VERSION_KEY = "modules"


# ── Internal models (full secrets) ───────────────────────────────────────────


class NextcloudModuleSettings(BaseModel):
    enabled: bool = False


class PhotosModuleSettings(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
            "image/heif",
            "image/gif",
        ]
    )
    strip_gps: bool = True


class AllModuleSettings(BaseModel):
    nextcloud: NextcloudModuleSettings = Field(default_factory=NextcloudModuleSettings)
    photos: PhotosModuleSettings = Field(default_factory=PhotosModuleSettings)


# ── OUT models ────────────────────────────────────────────────────────────────


class NextcloudModuleOut(BaseModel):
    enabled: bool


class PhotosModuleOut(BaseModel):
    enabled: bool
    widget_limit: int
    max_size_mb: int
    allowed_mime: list[str]
    strip_gps: bool


class AllModuleSettingsOut(BaseModel):
    nextcloud: NextcloudModuleOut
    photos: PhotosModuleOut


# ── IN models ─────────────────────────────────────────────────────────────────


class NextcloudModuleIn(BaseModel):
    enabled: bool


class PhotosModuleIn(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(default_factory=list)
    strip_gps: bool = True


# ── Storage ───────────────────────────────────────────────────────────────────


def load_modules() -> AllModuleSettings:
    now = time.monotonic()
    if _modules_cache.get("data") and now - _modules_cache.get("fetched_at", 0) < _CACHE_TTL:
        return _modules_cache["data"]

    if _MODULES_FILE.exists():
        try:
            data = AllModuleSettings.model_validate_json(_MODULES_FILE.read_text("utf-8"))
            _modules_cache["data"] = data
            _modules_cache["fetched_at"] = now
            return data
        except Exception as exc:
            logger.warning("modules.settings_parse_failed", path=str(_MODULES_FILE), error=str(exc))

    data = AllModuleSettings()
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = now
    return data


async def load_modules_shared(redis: Redis) -> AllModuleSettings:
    current_version = await get_version(redis, _CACHE_VERSION_KEY)
    if (
        _modules_cache.get("data")
        and _modules_cache.get("version") == current_version
        and time.monotonic() - _modules_cache.get("fetched_at", 0) < _CACHE_TTL
    ):
        return _modules_cache["data"]

    if _modules_cache.get("version") != current_version:
        _modules_cache.clear()
    data = load_modules()
    _modules_cache["data"] = data
    _modules_cache["fetched_at"] = time.monotonic()
    _modules_cache["version"] = current_version
    return data


def _save_modules(m: AllModuleSettings) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = m.model_dump_json(indent=2).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(prefix=".modules.", suffix=".json.tmp", dir=str(_SETTINGS_DIR))
    try:
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, _MODULES_FILE)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    _modules_cache.clear()


def invalidate_modules_cache() -> None:
    _modules_cache.clear()


# ── Endpoints ─────────────────────────────────────────────────────────────────


def _photos_out(m: PhotosModuleSettings) -> PhotosModuleOut:
    return PhotosModuleOut(
        enabled=m.enabled,
        widget_limit=m.widget_limit,
        max_size_mb=m.max_size_mb,
        allowed_mime=list(m.allowed_mime),
        strip_gps=m.strip_gps,
    )


@router.get("/modules", response_model=AllModuleSettingsOut)
async def get_modules_for_ui(_: CurrentUser, redis: RedisDep) -> AllModuleSettingsOut:
    m = await load_modules_shared(redis)
    return AllModuleSettingsOut(
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
        photos=_photos_out(m.photos),
    )


@router.get("/admin/modules", response_model=AllModuleSettingsOut)
async def get_module_settings(_: AdminDep, redis: RedisDep) -> AllModuleSettingsOut:
    m = await load_modules_shared(redis)
    return AllModuleSettingsOut(
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
        photos=_photos_out(m.photos),
    )


@router.put("/admin/modules/photos", response_model=PhotosModuleOut)
async def update_photos_module(
    data: PhotosModuleIn,
    admin: AdminDep,
    redis: RedisDep,
) -> PhotosModuleOut:
    m = await load_modules_shared(redis)
    updated = PhotosModuleSettings(
        enabled=data.enabled,
        widget_limit=data.widget_limit,
        max_size_mb=data.max_size_mb,
        allowed_mime=data.allowed_mime or m.photos.allowed_mime,
        strip_gps=data.strip_gps,
    )
    m.photos = updated
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    await push_audit_event(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_type="module",
        resource_id="photos",
        metadata={"module": "photos", "enabled": updated.enabled},
    )
    logger.info("modules.photos_updated", enabled=updated.enabled)
    return _photos_out(updated)


@router.put("/admin/modules/nextcloud", response_model=NextcloudModuleOut)
async def update_nextcloud_module(
    data: NextcloudModuleIn,
    admin: AdminDep,
    redis: RedisDep,
) -> NextcloudModuleOut:
    m = await load_modules_shared(redis)
    m.nextcloud = NextcloudModuleSettings(enabled=data.enabled)
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    from app.services.nextcloud import invalidate_nc_service

    await invalidate_nc_service()
    await push_audit_event(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_type="module",
        resource_id="nextcloud",
        metadata={"module": "nextcloud", "enabled": data.enabled},
    )
    logger.info("modules.nextcloud_updated", enabled=data.enabled)
    return NextcloudModuleOut(enabled=data.enabled)
