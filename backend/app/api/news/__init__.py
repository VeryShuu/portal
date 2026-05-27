"""News API package.

Thin HTTP layer split into per-domain routers:

- ``routes`` — main news CRUD (list/get/create/update/delete/restore/purge/versions)
- ``media`` — cover, gallery, attachments and inline-media uploads/serving
- ``export`` — HTML / Markdown / PDF export

Business logic lives in :mod:`app.services.news`; per-router data access lives
in :mod:`app.api.news.repo`.
"""

from __future__ import annotations

from fastapi import APIRouter

from .export import router as _export_router
from .media import router as _media_router
from .poll import router as _poll_router
from .routes import router as _routes_router

router = APIRouter(tags=["news"])
router.include_router(_routes_router, prefix="/news")
router.include_router(_media_router, prefix="/news")
router.include_router(_export_router, prefix="/news")
router.include_router(_poll_router, prefix="/news")

__all__ = ["router"]
