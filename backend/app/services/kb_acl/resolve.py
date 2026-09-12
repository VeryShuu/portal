"""Точечный разбор прав одного раздела/статьи + require_* хелперы."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle, KbArticlePermission, KbSection
from app.models.user import User

from ._common import (
    _PERM_RANK,
    PERM_MANAGER,
    _cache_key,
    _get_cached,
    _set_cached,
    _subject_ids_for_user,
    perm_gte,
)


async def _resolve_section_via_cte(
    db: AsyncSession, section_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Один рекурсивный CTE-запрос: все предки + их права за один SELECT."""
    if not subject_ids:
        return None
    result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, inherit_permissions, 0 AS depth
                FROM kb_sections WHERE id = :section_id AND deleted_at IS NULL
                UNION ALL
                SELECT s.id, s.parent_id, s.inherit_permissions, a.depth + 1
                FROM kb_sections s JOIN ancestors a ON s.id = a.parent_id
                WHERE s.deleted_at IS NULL AND a.inherit_permissions = TRUE AND a.depth < 20
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
