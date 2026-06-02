"""Global Search API: FTS + pg_trgm по KB, новостям, ярлыкам, пользователям.

Тонкий HTTP-слой: парсинг параметров + диспетчеризация в `services.search`
(single-type через request-scoped session, multi-type — параллельный fan-out).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep, SessionFactoryDep
from app.schemas.kb import SearchResponse, SuggestResponse
from app.services.search import run_multi_search, run_suggest
from app.services.search.entities import (
    search_articles,
    search_links,
    search_news,
    search_users,
)

router = APIRouter(prefix="/search", tags=["search"])

_SEARCH_TYPES = ("article", "news", "link", "user")


@router.get(
    "",
    response_model=SearchResponse,
    summary="Глобальный поиск",
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def global_search(
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
    session_factory: SessionFactoryDep,
    q: str = Query(min_length=1, max_length=200),
    type_filter: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    author_id: UUID | None = None,
    department: str | None = None,
) -> SearchResponse:
    if type_filter and type_filter in _SEARCH_TYPES:
        search_types = {type_filter}
    else:
        search_types = set(_SEARCH_TYPES)

    if len(search_types) > 1:
        return await run_multi_search(
            session_factory,
            search_types=search_types,
            q=q,
            user=user,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date,
            author_id=author_id,
            department=department,
        )

    # ── Single-type: ранжированная пагинация через request-scoped session ──
    if "article" in search_types:
        total, items = await search_articles(
            db,
            q=q,
            user=user,
            from_date=from_date,
            to_date=to_date,
            author_id=author_id,
            limit=limit,
            offset=offset,
            rank_order=True,
        )
    elif "news" in search_types:
        total, items = await search_news(
            db,
            q=q,
            user=user,
            from_date=from_date,
            to_date=to_date,
            author_id=author_id,
            department=department,
            limit=limit,
            offset=offset,
            rank_order=True,
        )
    elif "link" in search_types:
        total, items = await search_links(db, q=q, limit=limit, offset=offset, ordered=False)
    else:
        total, items = await search_users(
            db, q=q, department=department, limit=limit, offset=offset, ordered=False
        )
    return SearchResponse(items=items, total=total, query=q)


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    summary="Typeahead подсказки",
    dependencies=[Depends(RateLimiter(times=120, minutes=1))],
)
async def search_suggest(
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=100),
) -> SuggestResponse:
    return await run_suggest(db, redis, q=q, user=user)
