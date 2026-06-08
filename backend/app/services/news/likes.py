"""News likes (reactions): toggle + state queries.

Лайк — hard-delete toggle (одна строка на пару ``(news_id, user_id)``), по
аналогии с ``news_poll_voters``. Денормализованный счётчик ``news.like_count``
поддерживается в той же транзакции; декремент защищён ``GREATEST(..., 0)``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News, NewsLike
from app.schemas.news import NewsLikeState


async def _get_like_count(db: AsyncSession, news_id: uuid.UUID) -> int:
    res = await db.execute(select(News.like_count).where(News.id == news_id))
    return res.scalar_one()


async def like_news(db: AsyncSession, *, news_id: uuid.UUID, user_id: uuid.UUID) -> NewsLikeState:
    stmt = (
        pg_insert(NewsLike)
        .values(news_id=news_id, user_id=user_id)
        .on_conflict_do_nothing(constraint="uq_news_likes_news_user")
    )
    res = await db.execute(stmt)
    if res.rowcount and res.rowcount > 0:  # type: ignore[attr-defined]
        await db.execute(
            update(News).where(News.id == news_id).values(like_count=News.like_count + 1)
        )
    await db.commit()
    return NewsLikeState(like_count=await _get_like_count(db, news_id), liked_by_me=True)


async def unlike_news(db: AsyncSession, *, news_id: uuid.UUID, user_id: uuid.UUID) -> NewsLikeState:
    res = await db.execute(
        delete(NewsLike).where(NewsLike.news_id == news_id, NewsLike.user_id == user_id)
    )
    if res.rowcount and res.rowcount > 0:  # type: ignore[attr-defined]
        await db.execute(
            update(News)
            .where(News.id == news_id)
            .values(like_count=func.greatest(News.like_count - 1, 0))
        )
    await db.commit()
    return NewsLikeState(like_count=await _get_like_count(db, news_id), liked_by_me=False)


async def is_liked_by(db: AsyncSession, *, news_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    res = await db.execute(
        select(NewsLike.id).where(NewsLike.news_id == news_id, NewsLike.user_id == user_id)
    )
    return res.first() is not None


async def get_liked_news_ids(
    db: AsyncSession, *, user_id: uuid.UUID, news_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    ids = list(news_ids)
    if not ids:
        return set()
    res = await db.execute(
        select(NewsLike.news_id).where(NewsLike.user_id == user_id, NewsLike.news_id.in_(ids))
    )
    return set(res.scalars().all())
