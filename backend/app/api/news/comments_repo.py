"""Data access for news comments (SQL kept out of the HTTP layer).

Mirror of :mod:`app.api.kb.comments_repo`; the only addition is the
denormalised ``news.comment_count`` counter maintained in the same transaction
as the create/delete mutation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News, NewsComment
from app.models.user import User


async def count_active_comments(db: AsyncSession, news_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.count()).where(
            NewsComment.news_id == news_id,
            NewsComment.deleted_at.is_(None),
        )
    )
    return res.scalar_one()


async def list_comments(
    db: AsyncSession, news_id: uuid.UUID, *, limit: int, offset: int
) -> Sequence[NewsComment]:
    res = await db.execute(
        select(NewsComment)
        .where(NewsComment.news_id == news_id)
        .order_by(NewsComment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


async def get_comment_authors(
    db: AsyncSession, author_ids: set[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not author_ids:
        return {}
    res = await db.execute(select(User).where(User.id.in_(author_ids)))
    return {u.id: u for u in res.scalars()}


async def get_comment(
    db: AsyncSession, *, news_id: uuid.UUID, comment_id: uuid.UUID
) -> NewsComment | None:
    res = await db.execute(
        select(NewsComment).where(
            NewsComment.id == comment_id,
            NewsComment.news_id == news_id,
        )
    )
    return res.scalar_one_or_none()


async def increment_comment_count(db: AsyncSession, news_id: uuid.UUID) -> None:
    await db.execute(
        update(News).where(News.id == news_id).values(comment_count=News.comment_count + 1)
    )


async def decrement_comment_count(db: AsyncSession, news_id: uuid.UUID) -> None:
    await db.execute(
        update(News)
        .where(News.id == news_id)
        .values(comment_count=func.greatest(News.comment_count - 1, 0))
    )
