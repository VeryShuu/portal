"""Bootstrap endpoint — агрегирует все данные, необходимые для первой отрисовки SPA.

Заменяет 5 независимых запросов (/auth/me, /branding/settings, /modules,
/portal/gallery-links, /notifications/unread-count) одним параллельным вызовом.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.modules import (
    AllModuleSettingsOut,
    DirectoriesModuleOut,
    ErpSyncModuleOut,
    HelpdeskModuleOut,
    MeetingsModuleSettings,
    NextcloudModuleOut,
    PhotosModuleSettings,
    SignatureModuleOut,
    _meetings_out,
    _photos_out,
    load_modules_shared,
)
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.system_config import (
    GalleryLinksOut,
    load_system_settings,
    load_system_settings_shared,
)
from app.schemas.branding import BrandingSettings, BrandingSettingsOut
from app.schemas.user import UserMe
from app.services import branding_assets
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
    meetings=_meetings_out(MeetingsModuleSettings()),
    directories=DirectoriesModuleOut(enabled=False),
    signature=SignatureModuleOut(enabled=False),
    helpdesk=HelpdeskModuleOut(enabled=False),
    erp_sync=ErpSyncModuleOut(enabled=False),
)


class BootstrapOut(BaseModel):
    user: UserMe
    branding: BrandingSettingsOut
    modules: AllModuleSettingsOut
    gallery_links: GalleryLinksOut
    unread_count: int
    # Косметический флаг членства в helpdesk_agents (не атрибут пользователя).
    # Бэкенд-проверка агентства — всегда через SELECT в helpdesk_agents
    # (require_helpdesk_agent), этому флагу не доверяется (ТЗ §4.5, §7.2).
    is_helpdesk_agent: bool = False


def _build_branding() -> BrandingSettingsOut:
    s = branding_assets.load_settings()
    sys = load_system_settings()
    iframe_origins: list[str] = []
    if sys.video_gallery_url:
        iframe_origins.append(sys.video_gallery_url)
    return BrandingSettingsOut(
        **s.model_dump(),
        has_favicon=branding_assets.find_file("favicon", branding_assets.FAVICON_EXTS) is not None,
        has_login_bg=branding_assets.find_file("login-bg", branding_assets.ALL_EXTS) is not None,
        has_logo=branding_assets.find_file("logo", branding_assets.ALL_EXTS) is not None,
        allowed_iframe_origins=iframe_origins,
        has_hero_bg_morning=branding_assets.find_file("hero-bg-morning", branding_assets.ALL_EXTS)
        is not None,
        has_hero_bg_day=branding_assets.find_file("hero-bg-day", branding_assets.ALL_EXTS)
        is not None,
        has_hero_bg_evening=branding_assets.find_file("hero-bg-evening", branding_assets.ALL_EXTS)
        is not None,
    )


async def _is_helpdesk_agent(user_id: uuid.UUID, role: str | None) -> bool:
    """Проверяет членство пользователя в ``helpdesk_agents``.

    Админ — суперсет агента (см. ``require_helpdesk_agent`` в deps.py).
    Открывает **собственную** сессию: bootstrap запускает несколько DB-задач
    в ``asyncio.gather``, а одна ``AsyncSession`` запрещает конкурентный доступ
    (SQLAlchemy ISCE) — поэтому каждая DB-задача работает в изолированной
    сессии, как в ``app/api/health.py``.
    """
    if role == "admin":
        return True
    from app.models.helpdesk import HelpdeskAgent

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user_id)
        )
        return res.first() is not None


async def _fetch_unread_count(user_id: uuid.UUID) -> int:
    """Счётчик непрочитанных уведомлений в собственной сессии (см. _is_helpdesk_agent)."""
    async with AsyncSessionLocal() as session:
        return await get_unread_count(session, user_id)


@router.get("/bootstrap", response_model=BootstrapOut, summary="Bootstrap данные для SPA")
async def bootstrap(
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> BootstrapOut:
    # NB: ``db`` (request-scoped AsyncSession) НЕ используется для параллельных
    # DB-чтений ниже — SQLAlchemy запрещает конкурентные операции на одной
    # async-сессии (ISCE), что проявлялось как плавающий
    # ``bootstrap.is_helpdesk_agent_failed`` (лог продакшена). Каждая DB-задача
    # открывает собственную сессию через ``_is_helpdesk_agent`` /
    # ``_fetch_unread_count``. ``db`` остаётся в сигнатуре, т.к. его получение
    # запускает транзакцию и даёт CurrentUser через ту же сессию.

    async def _get_modules() -> AllModuleSettingsOut:
        m = await load_modules_shared(redis)
        return AllModuleSettingsOut(
            nextcloud=NextcloudModuleOut(enabled=m.nextcloud.enabled),
            photos=_photos_out(m.photos),
            meetings=_meetings_out(m.meetings),
            directories=DirectoriesModuleOut(enabled=m.directories.enabled),
            signature=SignatureModuleOut(enabled=m.signature.enabled),
            helpdesk=HelpdeskModuleOut(enabled=m.helpdesk.enabled),
            erp_sync=ErpSyncModuleOut(enabled=m.erp_sync.enabled),
        )

    async def _get_gallery_links() -> GalleryLinksOut:
        s = await load_system_settings_shared(redis)
        return GalleryLinksOut(
            photo_gallery_url=s.photo_gallery_url or None,
            photo_gallery_mode=s.photo_gallery_mode,
            photo_gallery_new_tab=s.photo_gallery_new_tab,
            video_gallery_url=s.video_gallery_url or None,
        )

    modules_res, gallery_res, unread_res, is_agent_res = await asyncio.gather(
        _get_modules(),
        _get_gallery_links(),
        _fetch_unread_count(user.id),
        _is_helpdesk_agent(user.id, user.role),
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

    if isinstance(is_agent_res, BaseException):
        logger.warning("bootstrap.is_helpdesk_agent_failed", error=str(is_agent_res))
        is_agent_res = False

    try:
        branding = await asyncio.to_thread(_build_branding)
    except Exception as exc:
        logger.warning("bootstrap.branding_failed", error=str(exc))
        branding = BrandingSettingsOut(
            **BrandingSettings().model_dump(),
            has_favicon=False,
            has_login_bg=False,
            has_logo=False,
            allowed_iframe_origins=[],
            has_hero_bg_morning=False,
            has_hero_bg_day=False,
            has_hero_bg_evening=False,
        )

    return BootstrapOut(
        user=UserMe.model_validate(user),
        branding=branding,
        modules=modules_res,
        gallery_links=gallery_res,
        unread_count=unread_res,
        is_helpdesk_agent=is_agent_res,
    )
