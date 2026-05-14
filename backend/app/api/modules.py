"""HTTP controller for runtime module configuration.

Storage and pure pydantic models live in `app.core.modules_config`.
This module owns only HTTP DTOs (IN/OUT) and FastAPI endpoints.

Re-exports of storage names are kept here for backward compatibility
with existing call sites and tests that patch `app.api.modules.*`.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, CurrentUser, RedisDep
from app.core.cache_version import bump_version
from app.core.logging import get_logger
from app.core.modules_config import (
    _CACHE_TTL,
    _CACHE_VERSION_KEY,
    _MODULES_FILE,
    _SETTINGS_DIR,
    AllModuleSettings,
    NextcloudModuleSettings,
    PhotosModuleSettings,
    _modules_cache,
    _save_modules,
    invalidate_modules_cache,
    load_modules,
    load_modules_shared,
)
from app.services.audit import push_audit_event

__all__ = [
    "_CACHE_TTL",
    "_CACHE_VERSION_KEY",
    "_MODULES_FILE",
    "_SETTINGS_DIR",
    "AllModuleSettings",
    "AllModuleSettingsOut",
    "NextcloudModuleIn",
    "NextcloudModuleOut",
    "NextcloudModuleSettings",
    "PhotosModuleIn",
    "PhotosModuleOut",
    "PhotosModuleSettings",
    "_modules_cache",
    "_photos_out",
    "_save_modules",
    "photos_module_out",
    "invalidate_modules_cache",
    "load_modules",
    "load_modules_shared",
    "router",
]

logger = get_logger(__name__)
router = APIRouter(tags=["modules"])


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


# ── Endpoints ─────────────────────────────────────────────────────────────────


def _photos_out(m: PhotosModuleSettings) -> PhotosModuleOut:
    return PhotosModuleOut(
        enabled=m.enabled,
        widget_limit=m.widget_limit,
        max_size_mb=m.max_size_mb,
        allowed_mime=list(m.allowed_mime),
        strip_gps=m.strip_gps,
    )


photos_module_out = _photos_out


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
