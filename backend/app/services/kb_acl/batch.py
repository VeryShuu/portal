"""Батч-резолв ACL для списков разделов/статей + filter_accessible_*."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle, KbArticlePermission, KbSection
from app.models.user import User

from ._common import (
    _ACL_TTL,
    _PERM_RANK,
    PERM_MANAGER,
    _cache_key,
    _subject_ids_for_user,
    logger,
)
from .resolve import resolve_article_permission, resolve_section_permission


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


def _best_perm(perms: list[str]) -> str | None:
    """Highest-ranked permission in the list, or None when empty."""
    return max(perms, key=lambda p: _PERM_RANK.get(p, 0)) if perms else None


async def _mget_acl_cache(
    redis: Redis, cache_keys: list[str], count: int, log_label: str
) -> list[str | None]:
    """Bulk Redis MGET normalised to exactly ``count`` entries (None on error)."""
    try:
        cached_values: list[str | None] = await redis.mget(*cache_keys)
    except Exception as exc:
        logger.debug(log_label, exc_info=exc)
        cached_values = [None] * count
    if not isinstance(cached_values, (list, tuple)) or len(cached_values) != count:
        cached_values = [None] * count
    return list(cached_values)


def _partition_cached(
    entities: list,
    cached_values: list[str | None],
    user_id: uuid.UUID,
    result: dict[uuid.UUID, str | None],
) -> list:
    """Split entities into resolved (owner/cache hit) vs cache-miss.

    Resolved entries are written into ``result``; misses are returned.
    Works for both sections and articles (both expose ``created_by``/``id``).
    """
    uncached = []
    for entity, cached in zip(entities, cached_values, strict=False):
        if entity.created_by == user_id:
            result[entity.id] = PERM_MANAGER
        elif cached is not None:
            result[entity.id] = cached if cached != "none" else None
        else:
            uncached.append(entity)
    return uncached


async def _cache_uncached_as_none(
    redis: Redis,
    user_id: uuid.UUID,
    kind: str,
    uncached: list,
    result: dict[uuid.UUID, str | None],
    log_label: str,
) -> None:
    """Persist 'none' for every cache-miss entity and mark it None in result."""
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for entity in uncached:
                pipe.setex(_cache_key(user_id, kind, entity.id), _ACL_TTL, "none")
            await pipe.execute()
    except Exception as exc:
        logger.debug(log_label, exc_info=exc)
    for entity in uncached:
        result[entity.id] = None


async def _write_perm_cache(redis: Redis, pipe_data: list[tuple[str, str]], log_label: str) -> None:
    """Write resolved (key, value) permission pairs back via a Redis pipeline."""
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for key, val in pipe_data:
                pipe.setex(key, _ACL_TTL, val)
            await pipe.execute()
    except Exception as exc:
        logger.debug(log_label, exc_info=exc)


async def _resolve_sections_via_db(
    db: AsyncSession, uncached: list[KbSection], subject_ids: list[str]
) -> dict[uuid.UUID, list[str]]:
    """One recursive CTE: all matching permissions per root section."""
    uncached_ids = [s.id for s in uncached]
    db_result = await db.execute(
        text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, inherit_permissions,
                       id AS root_section_id, 0 AS depth
                FROM kb_sections WHERE id = ANY(:section_ids)
                UNION ALL
                SELECT s.id, s.parent_id, s.inherit_permissions,
                       a.root_section_id, a.depth + 1
                FROM kb_sections s JOIN ancestors a ON s.id = a.parent_id
                WHERE a.inherit_permissions = TRUE AND a.depth < 20
            )
            SELECT a.root_section_id, p.permission
            FROM ancestors a
            JOIN kb_section_permissions p ON p.section_id = a.id
            WHERE p.subject_id = ANY(:sids)
        """),
        {"section_ids": [str(sid) for sid in uncached_ids], "sids": subject_ids},
    )

    perms_by_root: dict[uuid.UUID, list[str]] = {s.id: [] for s in uncached}
    for row in db_result.fetchall():
        root_id = uuid.UUID(str(row[0]))
        if root_id in perms_by_root:
            perms_by_root[root_id].append(row[1])
    return perms_by_root


async def batch_resolve_section_permissions(
    user: User,
    sections: list[KbSection],
    db: AsyncSession,
    redis: Redis,
) -> dict[uuid.UUID, str | None]:
    """Return {section_id: best_permission} for all sections in one pass.

    Mirrors batch_resolve_folder_permissions in files_acl.py:
    1. Admins → 'manager' without any DB/Redis hit.
    2. Short-circuit created_by == user.
    3. Bulk Redis MGET for the rest.
    4. Single CTE query for all cache-miss sections.
    5. Write resolved values back via Redis pipeline.
    """
    if user.role == "admin":
        return {s.id: PERM_MANAGER for s in sections}
    if not sections:
        return {}

    result: dict[uuid.UUID, str | None] = {}
    cache_keys = [_cache_key(user.id, "section", s.id) for s in sections]
    cached_values = await _mget_acl_cache(
        redis,
        cache_keys,
        len(sections),
        "Redis is unavailable for batch_resolve_section_permissions mget",
    )
    uncached = _partition_cached(sections, cached_values, user.id, result)

    if not uncached:
        return result

    subject_ids = await _subject_ids_for_user(user)
    if not subject_ids:
        await _cache_uncached_as_none(
            redis,
            user.id,
            "section",
            uncached,
            result,
            "Redis is unavailable for batch_resolve_section_permissions pipeline",
        )
        return result

    perms_by_root = await _resolve_sections_via_db(db, uncached, subject_ids)

    pipe_data: list[tuple[str, str]] = []
    for s in uncached:
        best = _best_perm(perms_by_root.get(s.id, []))
        result[s.id] = best
        pipe_data.append((_cache_key(user.id, "section", s.id), best if best else "none"))

    await _write_perm_cache(
        redis,
        pipe_data,
        "Redis is unavailable for batch_resolve_section_permissions pipeline write",
    )
    return result


async def _resolve_direct_articles(
    db: AsyncSession,
    user: User,
    direct_articles: list[KbArticle],
    subject_ids: list[str],
    result: dict[uuid.UUID, str | None],
) -> list[tuple[str, str]]:
    """Resolve articles with their own ACL via a single batch query."""
    direct_ids = [a.id for a in direct_articles]
    db_result = await db.execute(
        select(KbArticlePermission.article_id, KbArticlePermission.permission).where(
            KbArticlePermission.article_id.in_(direct_ids),
            KbArticlePermission.subject_id.in_(subject_ids),
        )
    )
    perms_by_art: dict[uuid.UUID, list[str]] = {a.id: [] for a in direct_articles}
    for row in db_result.fetchall():
        art_id = uuid.UUID(str(row[0]))
        if art_id in perms_by_art:
            perms_by_art[art_id].append(row[1])

    pipe_data: list[tuple[str, str]] = []
    for a in direct_articles:
        best = _best_perm(perms_by_art.get(a.id, []))
        result[a.id] = best
        pipe_data.append((_cache_key(user.id, "article", a.id), best if best else "none"))
    return pipe_data


async def _resolve_inherit_articles(
    db: AsyncSession,
    redis: Redis,
    user: User,
    inherit_articles: list[KbArticle],
    result: dict[uuid.UUID, str | None],
) -> list[tuple[str, str]]:
    """Resolve inheriting articles by delegating to the section batch resolver."""
    section_ids = list({a.section_id for a in inherit_articles if a.section_id})
    sec_result = await db.execute(select(KbSection).where(KbSection.id.in_(section_ids)))
    sections_list = list(sec_result.scalars().all())
    sec_perms = await batch_resolve_section_permissions(user, sections_list, db, redis)

    pipe_data: list[tuple[str, str]] = []
    for a in inherit_articles:
        sec_perm = sec_perms.get(a.section_id) if a.section_id else None
        result[a.id] = sec_perm
        pipe_data.append((_cache_key(user.id, "article", a.id), sec_perm if sec_perm else "none"))
    return pipe_data


async def batch_resolve_article_permissions(
    user: User,
    articles: list[KbArticle],
    db: AsyncSession,
    redis: Redis,
) -> dict[uuid.UUID, str | None]:
    """Return {article_id: best_permission} for all articles in one pass.

    Algorithm:
    1. Admins → 'manager' without any DB/Redis hit.
    2. Short-circuit created_by == user.
    3. Bulk Redis MGET for the rest.
    4. For cache-miss articles:
       a. Non-inherit (or inherit without section): single batch query on
          kb_article_permissions.
       b. Inherit with section: load sections, delegate to
          batch_resolve_section_permissions (one CTE query).
    5. Write resolved values back via Redis pipeline.
    """
    if user.role == "admin":
        return {a.id: PERM_MANAGER for a in articles}
    if not articles:
        return {}

    result: dict[uuid.UUID, str | None] = {}
    cache_keys = [_cache_key(user.id, "article", a.id) for a in articles]
    cached_values = await _mget_acl_cache(
        redis,
        cache_keys,
        len(articles),
        "Redis is unavailable for batch_resolve_article_permissions mget",
    )
    uncached = _partition_cached(articles, cached_values, user.id, result)

    if not uncached:
        return result

    subject_ids = await _subject_ids_for_user(user)
    if not subject_ids:
        await _cache_uncached_as_none(
            redis,
            user.id,
            "article",
            uncached,
            result,
            "Redis is unavailable for batch_resolve_article_permissions pipeline",
        )
        return result

    direct_articles = [a for a in uncached if not a.inherit_permissions or not a.section_id]
    inherit_articles = [a for a in uncached if a.inherit_permissions and a.section_id]

    pipe_data: list[tuple[str, str]] = []
    if direct_articles:
        pipe_data += await _resolve_direct_articles(db, user, direct_articles, subject_ids, result)
    if inherit_articles:
        pipe_data += await _resolve_inherit_articles(db, redis, user, inherit_articles, result)

    await _write_perm_cache(
        redis,
        pipe_data,
        "Redis is unavailable for batch_resolve_article_permissions pipeline write",
    )
    return result
