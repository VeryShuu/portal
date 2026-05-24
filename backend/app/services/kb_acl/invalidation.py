"""Инвалидация кешированных KB-ACL записей в Redis."""

from __future__ import annotations

import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle

from ._common import _scan_and_delete

logger = logging.getLogger(__name__)


async def invalidate_section_cache(
    redis: Redis,
    section_id: uuid.UUID,
    db: AsyncSession | None = None,
) -> None:
    """Drop cached section permission entries for the given section and its descendants.

    When *db* is supplied also invalidates article-level cache entries for
    articles that inherit permissions from this section or its descendant sections
    that have inherit_permissions=True.
    This ensures that revoking a section grant takes effect immediately instead
    of waiting for the 5-minute TTL to expire.
    """
    try:
        if db is not None:
            descendants_result = await db.execute(
                text("""
                    WITH RECURSIVE descendants AS (
                        SELECT id, inherit_permissions FROM kb_sections
                        WHERE id = :section_id AND deleted_at IS NULL
                        UNION ALL
                        SELECT s.id, s.inherit_permissions FROM kb_sections s
                        JOIN descendants d ON s.parent_id = d.id
                        WHERE s.deleted_at IS NULL AND s.inherit_permissions = TRUE
                    )
                    SELECT id FROM descendants
                """),
                {"section_id": str(section_id)},
            )
            sec_ids = [row[0] for row in descendants_result.fetchall()]

            for s_id in sec_ids:
                await _scan_and_delete(redis, f"kb_acl:*:section:{s_id}")

            art_res = await db.execute(
                select(KbArticle.id).where(
                    KbArticle.section_id.in_(sec_ids),
                    KbArticle.inherit_permissions.is_(True),
                    KbArticle.deleted_at.is_(None),
                )
            )
            for (art_id,) in art_res.fetchall():
                await _scan_and_delete(redis, f"kb_acl:*:article:{art_id}")
        else:
            await _scan_and_delete(redis, f"kb_acl:*:section:{section_id}")
    except Exception as exc:
        # Не маскируем ошибки: устаревший ACL-кэш — угроза безопасности.
        logger.warning(
            "Failed to invalidate KB section ACL cache section_id=%s: %s",
            section_id,
            exc,
            exc_info=exc,
        )


async def invalidate_article_cache(redis: Redis, article_id: uuid.UUID) -> None:
    try:
        await _scan_and_delete(redis, f"kb_acl:*:article:{article_id}")
    except Exception as exc:
        logger.warning(
            "Failed to invalidate KB article ACL cache article_id=%s: %s",
            article_id,
            exc,
            exc_info=exc,
        )
