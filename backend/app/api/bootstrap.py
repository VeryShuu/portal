"""Bootstrap endpoint — агрегирует все данные, необходимые для первой отрисовки SPA.

Заменяет 5 независимых запросов (/auth/me, /branding/settings, /modules,
/portal/gallery-links, /notifications/unread-count) одним параллельным вызовом.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.branding import (
    _ALL_EXTS,
    _FAVICON_EXTS,
    BrandingSettingsOut,
    _find_file,
    _load_settings,
)
from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.modules import (
    AllModuleSettingsOut,
    NextcloudModuleOut,
    PhotosModuleSettings,
    _photos_out,
    load_modules_shared,
)
from app.core.logging import get_logger
from app.core.system_config import (
    GalleryLinksOut,
    load_system_settings,
    load_system_settings_shared,
)
from app.schemas.user import UserMe
from app.services.notifications import get_unread_count

router = APIRouter(tags=["bootstrap"])
logger = get_logger(__name__)

_DEFAULT_GALLERY = GalleryLinksOut(
    photo_gallery_url=None,
    photo_gallery_mode="external",
    photo_gallery_new_tab=False,
    video_gallery_url=None,
)
_DEFAULT_MODULES = AllModuleSettingsOut(
    nextcloud=NextcloudModuleOut(enabled=False),
    photos=_photos_out(PhotosModuleSettings()),
)


class BootstrapOut(BaseModel):
    user: UserMe
    branding: BrandingSettingsOut
    modules: AllModuleSettingsOut
    gallery_links: GalleryLinksOut
    unread_count: int


def _build_branding() -> BrandingSettingsOut:
    s = _load_settings()
    sys = load_system_settings()
    iframe_origins: list[str] = []
    if sys.video_gallery_url:
        iframe_origins.append(sys.video_gallery_url)
    return BrandingSettingsOut(
        **s.model_dump(),
        has_favicon=_find_file("favicon", _FAVICON_EXTS) is not None,
        has_login_bg=_find_file("login-bg", _ALL_EXTS) is not None,
        has_logo=_find_file("logo", _ALL_EXTS) is not None,
        allowed_iframe_origins=iframe_origins,
    )


@router.get("/bootstrap", response_model=BootstrapOut, summary="Bootstrap данные для SPA")
async def bootstrap(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> BootstrapOut:
    async def _get_modules() -> AllModuleSettingsOut:
        m = await load_modules_shared(redis)
        return AllModuleSettingsOut(
            nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
            photos=_photos_out(m.photos),
        )

    async def _get_gallery_links() -> GalleryLinksOut:
        s = await load_system_settings_shared(redis)
        return GalleryLinksOut(
            photo_gallery_url=s.photo_gallery_url or None,
            photo_gallery_mode=s.photo_gallery_mode,
            photo_gallery_new_tab=s.photo_gallery_new_tab,
            video_gallery_url=s.video_gallery_url or None,
        )

    async def _get_unread_count() -> int:
        return await get_unread_count(db, user.id)

    modules_res, gallery_res, unread_res = await asyncio.gather(
        _get_modules(),
        _get_gallery_links(),
        _get_unread_count(),
        return_exceptions=True,
    )

    if isinstance(modules_res, BaseException):
        logger.warning("bootstrap.modules_failed", error=str(modules_res))
        modules_res = _DEFAULT_MODULES

    if isinstance(gallery_res, BaseException):
        logger.warning("bootstrap.gallery_links_failed", error=str(gallery_res))
        gallery_res = _DEFAULT_GALLERY

    if isinstance(unread_res, BaseException):
        logger.warning("bootstrap.unread_count_failed", error=str(unread_res))
        unread_res = 0

    try:
        branding = await asyncio.to_thread(_build_branding)
    except Exception as exc:
        logger.warning("bootstrap.branding_failed", error=str(exc))
        from app.api.branding import BrandingSettings

        branding = BrandingSettingsOut(
            **BrandingSettings().model_dump(),
            has_favicon=False,
            has_login_bg=False,
            has_logo=False,
            allowed_iframe_origins=[],
        )

    return BootstrapOut(
        user=UserMe.model_validate(user),
        branding=branding,
        modules=modules_res,  # type: ignore[arg-type]
        gallery_links=gallery_res,  # type: ignore[arg-type]
        unread_count=unread_res,  # type: ignore[arg-type]
    )
