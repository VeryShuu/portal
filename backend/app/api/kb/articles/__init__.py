"""KB articles endpoints package.

Раньше — монолитный ``app/api/kb/articles.py`` (535 строк). Разложен на
тематические подмодули (см. ref.md, пункт 1.5):

- :mod:`._list` — ``GET /kb/articles`` (фильтры, поиск, пагинация).
- :mod:`._crud` — создание/чтение/обновление статьи и автосохранение
  черновика.
- :mod:`._trash` — удаление (soft), окончательное удаление и
  восстановление.

Все имена, которые мокируют тесты (``app.api.kb.articles.X``),
реэкспортированы здесь для обратной совместимости. Подмодули обращаются
к этим именам через ``from app.api.kb import articles as _articles`` и
``_articles.<name>``, чтобы ``unittest.mock.patch`` на пакетном уровне
влиял на runtime-вызовы.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.sanitize import clean_title, sanitize_markdown
from app.models.kb import (
    KbArticle,
    KbArticleFeedback,
    KbArticleTag,
    KbArticleVersion,
    KbSection,
    KbTag,
)
from app.services.audit import make_audit_emitter
from app.services.kb import record_article_view, set_article_tags
from app.services.kb_acl import (
    apply_article_visibility,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
)
from app.services.kb_trash import purge_article

from .._common import (
    _article_to_public,
    _get_article_or_404,
    _get_breadcrumbs,
    _slugify,
    build_users_map,
    user_ref,
)
from ._crud import router as _crud_router
from ._list import router as _list_router
from ._trash import router as _trash_router

_emit_audit = make_audit_emitter("kb_article")

router = APIRouter()
router.include_router(_list_router)
router.include_router(_crud_router)
router.include_router(_trash_router)

__all__ = [
    "KbArticle",
    "KbArticleFeedback",
    "KbArticleTag",
    "KbArticleVersion",
    "KbSection",
    "KbTag",
    "_article_to_public",
    "_emit_audit",
    "_get_article_or_404",
    "_get_breadcrumbs",
    "_slugify",
    "apply_article_visibility",
    "build_users_map",
    "clean_title",
    "purge_article",
    "record_article_view",
    "require_article_permission",
    "require_section_permission",
    "resolve_article_permission",
    "router",
    "sanitize_markdown",
    "set_article_tags",
    "user_ref",
]
