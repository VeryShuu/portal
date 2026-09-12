"""Photos API package — re-exports combined router."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import RedisDep
from app.core.modules_config import load_modules_shared

from .folders import router as _folders_router
from .import_scan import router as _import_scan_router
from .permissions import router as _permissions_router
from .photos import router as _photos_router
from .public_views import router as _public_views_router
from .sharing import router as _sharing_router
from .tags import router as _tags_router
from .thumbnails import router as _thumbnails_router
from .zip_jobs import router as _zip_jobs_router

__all__ = ["PhotosGuard", "photos_enabled_guard", "router"]


async def photos_enabled_guard(redis: RedisDep) -> None:
    """Жёсткий kill-switch модуля (PA-008, решение владельца 2026-09-02):
    выключенный Photos закрывает весь prefix /photos ДО auth и ACL — включая
    публичные share-ссылки, которые переживать выключение не должны."""
    modules = await load_modules_shared(redis)
    if not modules.photos.enabled:
        raise HTTPException(status_code=404, detail="Photos module disabled")


PhotosGuard = Depends(photos_enabled_guard)

router = APIRouter(prefix="/photos", tags=["photos"], dependencies=[PhotosGuard])

router.include_router(_folders_router)
router.include_router(_permissions_router)
router.include_router(_sharing_router)
router.include_router(_public_views_router)
router.include_router(_tags_router)
router.include_router(_thumbnails_router)
router.include_router(_zip_jobs_router)
router.include_router(_import_scan_router)
router.include_router(_photos_router)
