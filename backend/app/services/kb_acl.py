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

import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.kb import KbArticle, KbArticlePermission, KbSection, KbSectionPermission
from app.models.user import User

logger = get_logger(__name__)

_PERM_RANK = {"viewer": 1, "editor": 2, "manager": 3}
_ACL_TTL = 300  # 5 минут


def _perm_gte(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _PERM_RANK.get(actual, 0) >= _PERM_RANK.get(required, 99)


def _cache_key(user_id: uuid.UUID, resource: str, resource_id: uuid.UUID) -> str:
    return f"kb_acl:{user_id}:{resource}:{resource_id}"


async def _get_cached(redis: Redis, key: str) -> str | None:
    try:
        return await redis.get(key)
    except Exception:
        return None


async def _set_cached(redis: Redis, key: str, value: str) -> None:
    try:
        await redis.setex(key, _ACL_TTL, value)
    except Exception:
        pass


async def _scan_and_delete(redis: Redis, pattern: str, batch: int = 500) -> None:
    """Non-blocking inverse of redis.keys(): SCAN + pipelined DELETE.

    `redis.keys()` blocks the whole instance which is unacceptable for a 300-user
    portal; SCAN walks the keyspace cooperatively in O(1) per call.
    """
    keys_buf: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=batch):
        keys_buf.append(key)
        if len(keys_buf) >= batch:
            await redis.delete(*keys_buf)
            keys_buf.clear()
    if keys_buf:
        await redis.delete(*keys_buf)


async def invalidate_section_cache(redis: Redis, section_id: uuid.UUID) -> None:
    """Drop cached section permission entries for the given section.

    Article cache is left untouched here: it has its own narrow invalidation
    path triggered by article-level permission changes, so dropping all
    `article:*` entries on every section change is needlessly destructive.
    """
    try:
        await _scan_and_delete(redis, f"kb_acl:*:section:{section_id}")
    except Exception:
        pass


async def invalidate_article_cache(redis: Redis, article_id: uuid.UUID) -> None:
    try:
        await _scan_and_delete(redis, f"kb_acl:*:article:{article_id}")
    except Exception:
        pass


async def _subject_ids_for_user(user: User) -> list[str]:
    """Возвращает список subject_id: UUID пользователя + keycloak_id + keycloak_groups.

    Локальные пользователи (auth_source='local') не имеют keycloak_id, поэтому
    всегда включаем str(user.id) — он используется как subject_id при выдаче прав.
    """
    ids: list[str] = [str(user.id)]
    if user.keycloak_id:
        ids.append(user.keycloak_id)
    if hasattr(user, "keycloak_groups") and user.keycloak_groups:
        groups = user.keycloak_groups
        if isinstance(groups, list):
            ids.extend(str(g) for g in groups)
    return ids


async def _resolve_section_permissions_raw(
    db: AsyncSession, section_id: uuid.UUID, subject_ids: list[str]
) -> str | None:
    """Ищет лучшее право среди kb_section_permissions для данного раздела."""
    if not subject_ids:
        return None
    result = await db.execute(
        select(KbSectionPermission.permission)
        .where(
            KbSectionPermission.section_id == section_id,
            KbSectionPermission.subject_id.in_(subject_ids),
        )
    )
    perms = [row[0] for row in result.fetchall()]
    if not perms:
        return None
    return max(perms, key=lambda p: _PERM_RANK.get(p, 0))


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
        return "manager"
    if section.created_by == user.id:
        return "manager"

    cache_key = _cache_key(user.id, "section", section.id)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best: str | None = None

    current_id: uuid.UUID | None = section.id
    visited: set[uuid.UUID] = set()
    depth = 0

    while current_id and depth < 20:
        if current_id in visited:
            break
        visited.add(current_id)

        perm = await _resolve_section_permissions_raw(db, current_id, subject_ids)
        if perm and _PERM_RANK.get(perm, 0) > _PERM_RANK.get(best or "", 0):
            best = perm

        if best == "manager":
            break

        sec_result = await db.execute(select(KbSection).where(KbSection.id == current_id))
        sec = sec_result.scalar_one_or_none()
        if not sec:
            break
        current_id = sec.parent_id
        depth += 1

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
        return "manager"
    if article.created_by == user.id:
        return "manager"

    cache_key = _cache_key(user.id, "article", article.id)
    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        return cached if cached != "none" else None

    subject_ids = await _subject_ids_for_user(user)
    best: str | None = None

    if not article.inherit_permissions:
        if subject_ids:
            result = await db.execute(
                select(KbArticlePermission.permission)
                .where(
                    KbArticlePermission.article_id == article.id,
                    KbArticlePermission.subject_id.in_(subject_ids),
                )
            )
            perms = [row[0] for row in result.fetchall()]
            if perms:
                best = max(perms, key=lambda p: _PERM_RANK.get(p, 0))
    else:
        if article.section_id:
            sec_result = await db.execute(select(KbSection).where(KbSection.id == article.section_id))
            section = sec_result.scalar_one_or_none()
            if section:
                best = await resolve_section_permission(user, section, db, redis)
        else:
            if subject_ids:
                result = await db.execute(
                    select(KbArticlePermission.permission)
                    .where(
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
    if not _perm_gte(perm, required):
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
    if not _perm_gte(perm, required):
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
