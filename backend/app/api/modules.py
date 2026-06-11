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
    DirectoriesModuleSettings,
    MeetingsModuleSettings,
    NextcloudModuleSettings,
    PhotosModuleSettings,
    SignatureModuleSettings,
    _modules_cache,
    _save_modules,
    invalidate_modules_cache,
    load_modules,
    load_modules_shared,
)
from app.services.audit import make_audit_emitter

__all__ = [
    "_CACHE_TTL",
    "_CACHE_VERSION_KEY",
    "_MODULES_FILE",
    "_SETTINGS_DIR",
    "AllModuleSettings",
    "AllModuleSettingsOut",
    "DirectoriesModuleIn",
    "DirectoriesModuleOut",
    "DirectoriesModuleSettings",
    "MeetingsModuleIn",
    "MeetingsModuleOut",
    "MeetingsModuleSettings",
    "NextcloudModuleIn",
    "NextcloudModuleOut",
    "NextcloudModuleSettings",
    "PhotosModuleIn",
    "PhotosModuleOut",
    "PhotosModuleSettings",
    "SignatureModuleIn",
    "SignatureModuleOut",
    "SignatureModuleSettings",
    "_meetings_out",
    "_modules_cache",
    "_photos_out",
    "_save_modules",
    "invalidate_modules_cache",
    "load_modules",
    "load_modules_shared",
    "photos_module_out",
    "router",
]

logger = get_logger(__name__)
router = APIRouter(tags=["modules"])

_emit_audit = make_audit_emitter("module")


# ── OUT models ────────────────────────────────────────────────────────────────


class NextcloudModuleOut(BaseModel):
    enabled: bool


class PhotosModuleOut(BaseModel):
    enabled: bool
    widget_limit: int
    max_size_mb: int
    allowed_mime: list[str]
    strip_gps: bool
    max_share_ttl_days: int = 365


class MeetingsModuleOut(BaseModel):
    enabled: bool
    calendar_start_hour: int
    calendar_end_hour: int
    max_recurrence_horizon_days: int
    min_search_chars: int


class DirectoriesModuleOut(BaseModel):
    enabled: bool


class SignatureModuleOut(BaseModel):
    enabled: bool


class AllModuleSettingsOut(BaseModel):
    nextcloud: NextcloudModuleOut
    photos: PhotosModuleOut
    meetings: MeetingsModuleOut
    directories: DirectoriesModuleOut
    signature: SignatureModuleOut


# ── IN models ─────────────────────────────────────────────────────────────────


class NextcloudModuleIn(BaseModel):
    enabled: bool


class PhotosModuleIn(BaseModel):
    enabled: bool = True
    widget_limit: int = Field(default=8, ge=1, le=50)
    max_size_mb: int = Field(default=50, ge=1, le=500)
    allowed_mime: list[str] = Field(default_factory=list)
    strip_gps: bool = True
    max_share_ttl_days: int = Field(default=365, ge=1, le=365)


class MeetingsModuleIn(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = Field(default=8, ge=0, le=23)
    calendar_end_hour: int = Field(default=19, ge=1, le=24)
    max_recurrence_horizon_days: int = Field(default=31, ge=1, le=365)
    min_search_chars: int = Field(default=3, ge=1, le=10)


class DirectoriesModuleIn(BaseModel):
    enabled: bool = False


class SignatureModuleIn(BaseModel):
    enabled: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────


def _photos_out(m: PhotosModuleSettings) -> PhotosModuleOut:
    return PhotosModuleOut(
        enabled=m.enabled,
        widget_limit=m.widget_limit,
        max_size_mb=m.max_size_mb,
        allowed_mime=list(m.allowed_mime),
        strip_gps=m.strip_gps,
        max_share_ttl_days=m.max_share_ttl_days,
    )


photos_module_out = _photos_out


def _meetings_out(m: MeetingsModuleSettings) -> MeetingsModuleOut:
    return MeetingsModuleOut(
        enabled=m.enabled,
        calendar_start_hour=m.calendar_start_hour,
        calendar_end_hour=m.calendar_end_hour,
        max_recurrence_horizon_days=m.max_recurrence_horizon_days,
        min_search_chars=m.min_search_chars,
    )


@router.get("/modules", response_model=AllModuleSettingsOut)
async def get_modules_for_ui(_: CurrentUser, redis: RedisDep) -> AllModuleSettingsOut:
    m = await load_modules_shared(redis)
    return AllModuleSettingsOut(
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
        photos=_photos_out(m.photos),
        meetings=_meetings_out(m.meetings),
        directories=DirectoriesModuleOut(enabled=m.directories.enabled),
        signature=SignatureModuleOut(enabled=m.signature.enabled),
    )


@router.get("/admin/modules", response_model=AllModuleSettingsOut)
async def get_module_settings(_: AdminDep, redis: RedisDep) -> AllModuleSettingsOut:
    m = await load_modules_shared(redis)
    return AllModuleSettingsOut(
        nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
        photos=_photos_out(m.photos),
        meetings=_meetings_out(m.meetings),
        directories=DirectoriesModuleOut(enabled=m.directories.enabled),
        signature=SignatureModuleOut(enabled=m.signature.enabled),
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
        max_share_ttl_days=data.max_share_ttl_days,
    )
    m.photos = updated
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    await _emit_audit(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
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
    await _emit_audit(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_id="nextcloud",
        metadata={"module": "nextcloud", "enabled": data.enabled},
    )
    logger.info("modules.nextcloud_updated", enabled=data.enabled)
    return NextcloudModuleOut(enabled=data.enabled)


@router.put("/admin/modules/meetings", response_model=MeetingsModuleOut)
async def update_meetings_module(
    data: MeetingsModuleIn,
    admin: AdminDep,
    redis: RedisDep,
) -> MeetingsModuleOut:
    m = await load_modules_shared(redis)
    updated = MeetingsModuleSettings(
        enabled=data.enabled,
        calendar_start_hour=data.calendar_start_hour,
        calendar_end_hour=data.calendar_end_hour,
        max_recurrence_horizon_days=data.max_recurrence_horizon_days,
        min_search_chars=data.min_search_chars,
    )
    m.meetings = updated
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    await _emit_audit(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_id="meetings",
        metadata={"module": "meetings", "enabled": updated.enabled},
    )
    logger.info("modules.meetings_updated", enabled=updated.enabled)
    return _meetings_out(updated)


@router.put("/admin/modules/directories", response_model=DirectoriesModuleOut)
async def update_directories_module(
    data: DirectoriesModuleIn,
    admin: AdminDep,
    redis: RedisDep,
) -> DirectoriesModuleOut:
    m = await load_modules_shared(redis)
    m.directories = DirectoriesModuleSettings(enabled=data.enabled)
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    await _emit_audit(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_id="directories",
        metadata={"module": "directories", "enabled": data.enabled},
    )
    logger.info("modules.directories_updated", enabled=data.enabled)
    return DirectoriesModuleOut(enabled=data.enabled)


@router.put("/admin/modules/signature", response_model=SignatureModuleOut)
async def update_signature_module(
    data: SignatureModuleIn,
    admin: AdminDep,
    redis: RedisDep,
) -> SignatureModuleOut:
    m = await load_modules_shared(redis)
    m.signature = SignatureModuleSettings(enabled=data.enabled)
    _save_modules(m)
    await bump_version(redis, _CACHE_VERSION_KEY)
    await _emit_audit(
        redis,
        event_type="modules.toggled",
        user_id=str(admin.id),
        resource_id="signature",
        metadata={"module": "signature", "enabled": data.enabled},
    )
    logger.info("modules.signature_updated", enabled=data.enabled)
    return SignatureModuleOut(enabled=data.enabled)
