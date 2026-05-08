"""KB ACL: проверка прав доступа к разделам и статьям.

Алгоритм для статьи:
  1. portal admin  → permission = 'manager'
  2. created_by    → permission = 'manager'
  3. inherit_permissions = False → kb_article_permissions
  4. inherit_permissions = True  → рекурсивно вверх по kb_section_permissions
  5. None → нет доступа → 403

Уровни: viewer < editor < manager
"""

from __future__ import annotations

import contextlib
import uuid

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PERM_EDITOR, PERM_MANAGER, PERM_VIEWER
from app.core.logging import get_logger
from app.models.kb import KbArticle, KbArticlePermission, KbSection
from app.models.user import User
from app.services.acl_base import (
    get_cached as _get_cached,
)
from app.services.acl_base import (
    scan_and_delete as _scan_and_delete,
)
from app.services.acl_base import (
    set_cached as _set_cached,
)
from app.services.acl_base import (
    subject_ids_for_user as _subject_ids_for_user,
)

logger = get_logger(__name__)

_PERM_RANK = {PERM_VIEWER: 1, PERM_EDITOR: 2, PERM_MANAGER: 3}


def perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


# Backward-compatible alias (preferred name is perm_gte without underscore).
_perm_gte = perm_gte


def _cache_key(user_id: uuid.UUID, resource: str, resource_id: uuid.UUID) -> str:
    return f"kb_acl:{user_id}:{resource}:{resource_id}"


async def invalidate_section_cache(
    redis: Redis,
    section_id: uuid.UUID,
    db: AsyncSession | None = None,
) -> None:
    """Drop cached section permission entries for the given section.

    When *db* is supplied also invalidates article-level cache entries for
    articles that inherit permissions from this section (inherit_permissions=True).
    This ensures that revoking a section grant takes effect immediately instead
    of waiting for the 5-minute TTL to expire.
    """
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"kb_acl:*:section:{section_id}")

        if db is not None:
            art_res = await db.execute(
                select(KbArticle.id).where(
                    KbArticle.section_id == section_id,
                    KbArticle.inherit_permissions.is_(True),
                    KbArticle.deleted_at.is_(None),
                )
            )
            for (art_id,) in art_res.fetchall():
                await _scan_and_delete(redis, f"kb_acl:*:article:{art_id}")


async def invalidate_article_cache(redis: Redis, article_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):
        await _scan_and_delete(redis, f"kb_acl:*:article:{article_id}")


async def _resolve_section_via_cte(
    db: AsyncSession, section_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Один рекурсивный CTE-запрос: все предки + их права за один SELECT."""
    if not subject_ids:
        return None
    result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 0 AS depth
                FROM kb_sections WHERE id = :section_id
                UNION ALL
                SELECT s.id, s.parent_id, a.depth + 1
                FROM kb_sections s JOIN ancestors a ON s.id = a.parent_id
                WHERE a.depth < 20
            )
            SELECT p.permission
            FROM ancestors a
            JOIN kb_section_permissions p ON p.section_id = a.id
            WHERE p.subject_id = ANY(:sids)
            ORDER BY CASE p.permission
                WHEN 'manager' THEN 3
                WHEN 'editor'  THEN 2
                WHEN 'viewer'  THEN 1
                ELSE 0 END DESC
            LIMIT 1
        """),
        {"section_id": str(section_id), "sids": subject_ids},
    )
    row = result.fetchone()
    return row[0] if row else None


async def resolve_section_permission(
    user: User,
    section: KbSection,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    """Возвращает лучшее право пользователя на раздел (с рекурсией вверх).

    Returns: 'viewer' | 'editor' | 'manager' | None
    """
    if user.role == "admin":
        return PERM_MANAGER
    if section.created_by == user.id:
        return PERM_MANAGER

    cache_key = _cache_key(user.id, "section", section.id)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best = await _resolve_section_via_cte(db, section.id, subject_ids)

    await _set_cached(redis, cache_key, best if best else "none")
    return best


async def resolve_article_permission(
    user: User,
    article: KbArticle,
    db: AsyncSession,
    redis: Redis,
) -> str | None:
    """Возвращает лучшее право пользователя на статью.

    Returns: 'viewer' | 'editor' | 'manager' | None
    """
    if user.role == "admin":
        return PERM_MANAGER
    if article.created_by == user.id:
        return PERM_MANAGER

    cache_key = _cache_key(user.id, "article", article.id)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best: str | None = None

    if not article.inherit_permissions:
        if subject_ids:
            result = await db.execute(
                select(KbArticlePermission.permission).where(
                    KbArticlePermission.article_id == article.id,
                    KbArticlePermission.subject_id.in_(subject_ids),
                )
            )
            perms = [row[0] for row in result.fetchall()]
            if perms:
                best = max(perms, key=lambda p: _PERM_RANK.get(p, 0))
    else:
        if article.section_id:
            sec_result = await db.execute(
                select(KbSection).where(KbSection.id == article.section_id)
            )
            section = sec_result.scalar_one_or_none()
            if section:
                best = await resolve_section_permission(user, section, db, redis)
        else:
            if subject_ids:
                result = await db.execute(
                    select(KbArticlePermission.permission).where(
                        KbArticlePermission.article_id == article.id,
                        KbArticlePermission.subject_id.in_(subject_ids),
                    )
                )
                perms = [row[0] for row in result.fetchall()]
                if perms:
                    best = max(perms, key=lambda p: _PERM_RANK.get(p, 0))

    await _set_cached(redis, cache_key, best if best else "none")
    return best


async def require_article_permission(
    user: User,
    article: KbArticle,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> None:
    """Бросает HTTPException 403 если у пользователя нет нужного права."""
    from fastapi import HTTPException, status

    perm = await resolve_article_permission(user, article, db, redis)
    if not perm_gte(perm, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient KB permissions",
        )


async def require_section_permission(
    user: User,
    section: KbSection,
    required: str,
    db: AsyncSession,
    redis: Redis,
) -> None:
    from fastapi import HTTPException, status

    perm = await resolve_section_permission(user, section, db, redis)
    if not perm_gte(perm, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient KB permissions",
        )


async def filter_accessible_sections(
    user: User,
    sections: list[KbSection],
    db: AsyncSession,
    redis: Redis,
) -> list[KbSection]:
    """Фильтрует список разделов оставляя только доступные пользователю."""
    if user.role == "admin":
        return sections
    accessible = []
    for s in sections:
        perm = await resolve_section_permission(user, s, db, redis)
        if perm is not None:
            accessible.append(s)
    return accessible


async def filter_accessible_articles(
    user: User,
    articles: list[KbArticle],
    db: AsyncSession,
    redis: Redis,
) -> list[KbArticle]:
    """Фильтрует список статей оставляя только доступные пользователю."""
    if user.role == "admin":
        return articles
    accessible = []
    for a in articles:
        perm = await resolve_article_permission(user, a, db, redis)
        if perm is not None:
            accessible.append(a)
    return accessible
