"""Knowledge Base API package.

Original monoliths ``app/api/kb.py`` (1354 lines) and ``app/api/kb_extra.py``
(1040 lines) were split into focused submodules (see ref.md task 1.1.d).
API contracts (paths, methods, operationIds) remain identical — verified
via OpenAPI snapshot.
"""

from __future__ import annotations

from fastapi import APIRouter

from ._common import _get_article_or_404
from .articles import router as _articles_router
from .attachments import router as _attachments_router
from .comments import router as _comments_router
from .export_import import router as _export_import_router
from .feedback import router as _feedback_router
from .media import router as _media_router
from .permissions import router as _permissions_router
from .sections import router as _sections_router
from .suggestions import router as _suggestions_router
from .tags import router as _tags_router
from .versions import router as _versions_router

router = APIRouter()

router.include_router(_sections_router)
router.include_router(_tags_router)
router.include_router(_articles_router)
router.include_router(_versions_router)
router.include_router(_comments_router)
router.include_router(_suggestions_router)
router.include_router(_feedback_router)
router.include_router(_permissions_router)
router.include_router(_media_router)
router.include_router(_attachments_router)
router.include_router(_export_import_router)

__all__ = ["_get_article_or_404", "router"]
