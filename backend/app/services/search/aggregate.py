"""Search use-cases: multi-type parallel fan-out and typeahead suggestions.

Owns the orchestration that the thin API handlers delegate to: running the
per-entity queries, merging/sorting/paginating multi-type results, and building
the suggest list. KB visibility stays correct via ``apply_article_visibility``
(inside the entity queries) and ``filter_accessible_articles`` (suggest).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.kb import KbArticle
from app.models.news import News
from app.models.user import User
from app.schemas.kb import SearchResponse, SearchResultItem, SuggestResponse
from app.services.kb_acl import filter_accessible_articles
from app.services.news import news_targeting_conditions
from app.services.search.entities import (
    search_articles,
    search_links,
    search_news,
    search_users,
)
from app.services.search.filters import DATETIME_MIN_UTC

_EntityQuery = Callable[[AsyncSession], Awaitable[tuple[int, list[SearchResultItem]]]]


async def run_multi_search(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    search_types: set[str],
    q: str,
    user: User,
    limit: int,
    offset: int,
    from_date: datetime | None,
    to_date: datetime | None,
    author_id: UUID | None,
    department: str | None,
) -> SearchResponse:
    """Run the requested per-entity searches in parallel, merge and paginate.

    Each coroutine opens its own session (a single ``AsyncSession`` cannot run
    concurrent executes), fetches the first ``offset + limit`` rows ordered by
    recency, then results are merged, sorted by ``created_at`` and windowed.
    """
    fetch_limit = offset + limit

    async def _run(fn: _EntityQuery) -> tuple[int, list[SearchResultItem]]:
        async with session_factory() as sess:
            return await fn(sess)

    tasks: list[Awaitable[tuple[int, list[SearchResultItem]]]] = []
    if "article" in search_types:
        tasks.append(
            _run(
                lambda sess: search_articles(
                    sess,
                    q=q,
                    user=user,
                    from_date=from_date,
                    to_date=to_date,
                    author_id=author_id,
                    limit=fetch_limit,
                    offset=0,
                    rank_order=False,
                )
            )
        )
    if "news" in search_types:
        tasks.append(
            _run(
                lambda sess: search_news(
                    sess,
                    q=q,
                    user=user,
                    from_date=from_date,
                    to_date=to_date,
                    author_id=author_id,
                    department=department,
                    limit=fetch_limit,
                    offset=0,
                    rank_order=False,
                )
            )
        )
    if "link" in search_types:
        tasks.append(
            _run(lambda sess: search_links(sess, q=q, limit=fetch_limit, offset=0, ordered=True))
        )
    if "user" in search_types:
        tasks.append(
            _run(
                lambda sess: search_users(
                    sess, q=q, department=department, limit=fetch_limit, offset=0, ordered=True
                )
            )
        )

    gathered = await asyncio.gather(*tasks)
    total = sum(t for t, _ in gathered)
    results: list[SearchResultItem] = []
    for _, items in gathered:
        results.extend(items)
    results.sort(key=lambda r: r.created_at or DATETIME_MIN_UTC, reverse=True)
    return SearchResponse(items=results[offset : offset + limit], total=total, query=q)


async def run_suggest(
    db: AsyncSession,
    redis: Redis,
    *,
    q: str,
    user: User,
) -> SuggestResponse:
    """Build typeahead suggestions: up to 5 accessible KB titles, then news."""
    suggestions: list[str] = []

    article_r = await db.execute(
        select(KbArticle)
        .where(
            KbArticle.deleted_at.is_(None),
            KbArticle.status == "published",
            KbArticle.title.op("%")(q),
        )
        .order_by(func.similarity(KbArticle.title, q).desc())
        .limit(10)
    )
    raw_articles = article_r.scalars().all()
    accessible_articles = await filter_accessible_articles(user, list(raw_articles), db, redis)
    for article_obj in accessible_articles[:5]:
        suggestions.append(article_obj.title)

    news_conds: list[Any] = [
        News.deleted_at.is_(None),
        News.status == "published",
        News.title.op("%")(q),
    ]
    if user.role not in ("editor", "admin"):
        news_conds.extend(news_targeting_conditions(user))
    news_r = await db.execute(
        select(News.title)
        .where(*news_conds)
        .order_by(func.similarity(News.title, q).desc())
        .limit(5)
    )
    for (title,) in news_r:
        if title not in suggestions:
            suggestions.append(title)

    return SuggestResponse(suggestions=suggestions[:10])
