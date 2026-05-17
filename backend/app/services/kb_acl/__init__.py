"""KB ACL package.

Раньше — монолитный ``app/services/kb_acl.py`` (557 строк). Разложен
на подмодули по ответственности (см. ref.md, пункт 3.1):

- :mod:`._common` — ранжирование прав, cache-key, реэкспорты из ``acl_base``.
- :mod:`.invalidation` — инвалидация Redis-кеша по разделам/статьям.
- :mod:`.resolve` — точечный resolve и require_* хелперы.
- :mod:`.batch` — батч-резолв для списков + filter_accessible_*.
- :mod:`.visibility` — SQL push-down фильтрация ``apply_article_visibility``.

Алгоритм для статьи:
  1. portal admin  → permission = 'manager'
  2. created_by    → permission = 'manager'
  3. inherit_permissions = False → kb_article_permissions
  4. inherit_permissions = True  → рекурсивно вверх по kb_section_permissions
  5. None → нет доступа → 403

Уровни: viewer < editor < manager
"""

from __future__ import annotations

from ._common import (
    _ACL_TTL,
    _PERM_RANK,
    _cache_key,
    _perm_gte,
    _subject_ids_for_user,
    logger,
    perm_gte,
)
from .batch import (
    batch_resolve_article_permissions,
    batch_resolve_section_permissions,
    filter_accessible_articles,
    filter_accessible_sections,
)
from .invalidation import invalidate_article_cache, invalidate_section_cache
from .resolve import (
    _resolve_section_via_cte,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
    resolve_section_permission,
)
from .visibility import _accessible_sections_cte, apply_article_visibility

__all__ = [
    "_ACL_TTL",
    "_PERM_RANK",
    "_accessible_sections_cte",
    "_cache_key",
    "_perm_gte",
    "_resolve_section_via_cte",
    "_subject_ids_for_user",
    "apply_article_visibility",
    "batch_resolve_article_permissions",
    "batch_resolve_section_permissions",
    "filter_accessible_articles",
    "filter_accessible_sections",
    "invalidate_article_cache",
    "invalidate_section_cache",
    "logger",
    "perm_gte",
    "require_article_permission",
    "require_section_permission",
    "resolve_article_permission",
    "resolve_section_permission",
]
