"""Инвалидация кешированных KB-ACL записей в Redis."""

from __future__ import annotations

import contextlib
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle

from ._common import _scan_and_delete


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
