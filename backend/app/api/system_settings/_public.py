"""Public (non-admin) helpers + nextcloud status endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AdminDep, RedisDep
from app.core.system_config import (
    GalleryLinksOut,
    load_system_settings_shared,
)

router = APIRouter(tags=["system-settings"])


class StaffSettingsOut(BaseModel):
    phone_extract_regex: str


class NcStatusOut(BaseModel):
    ok: bool
    configured: bool
    server_reachable: bool
    nc_version: str | None
    auth_ok: bool
    webdav_ok: bool
    details: str | None


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
