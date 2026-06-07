"""Pure data-access helpers for the KB trash (soft-deleted articles).

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.kb import KbArticle, KbArticleFile, KbSection
from app.models.user import User


async def count_trashed(db: AsyncSession) -> int:
    res = await db.execute(
        select(func.count(KbArticle.id)).where(KbArticle.deleted_at.isnot(None))
    )
    return int(res.scalar() or 0)


async def count_trashed_due(db: AsyncSession, threshold: datetime) -> int:
    res = await db.execute(
        select(func.count(KbArticle.id)).where(
            KbArticle.deleted_at.isnot(None),
            KbArticle.deleted_at < threshold,
        )
    )
    return int(res.scalar() or 0)


async def list_trashed(
    db: AsyncSession, *, limit: int, offset: int
) -> Sequence[KbArticle]:
    res = await db.execute(
        select(KbArticle)
        .where(KbArticle.deleted_at.isnot(None))
        .order_by(KbArticle.deleted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


async def get_section_titles(
    db: AsyncSession, section_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not section_ids:
        return {}
    res = await db.execute(
        select(KbSection.id, KbSection.title).where(KbSection.id.in_(section_ids))
    )
    return {row[0]: row[1] for row in res.all()}


async def get_users(db: AsyncSession, user_ids: set[uuid.UUID]) -> Sequence[User]:
    if not user_ids:
        return []
    res = await db.execute(select(User).where(User.id.in_(user_ids)))
    return res.scalars().all()


async def get_file_stats(
    db: AsyncSession, article_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    res = await db.execute(
        select(
            KbArticleFile.article_id,
            func.count(KbArticleFile.id),
            func.coalesce(func.sum(KbArticleFile.size_bytes), 0),
        )
        .where(KbArticleFile.article_id.in_(article_ids))
        .group_by(KbArticleFile.article_id)
    )
    return {row[0]: (int(row[1]), int(row[2])) for row in res.all()}


async def get_trashed_with_tags(
    db: AsyncSession, article_id: uuid.UUID
) -> KbArticle | None:
    res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.isnot(None))
    )
    return res.scalar_one_or_none()


async def trashed_exists(db: AsyncSession, article_id: uuid.UUID) -> bool:
    res = await db.execute(
        select(KbArticle.id).where(
            KbArticle.id == article_id, KbArticle.deleted_at.isnot(None)
        )
    )
    return res.scalar_one_or_none() is not None
