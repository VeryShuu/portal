"""Global Search API: FTS + pg_trgm по KB, новостям, ярлыкам, пользователям."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, or_, select, text

from app.api.deps import CurrentUser, DbDep
from app.models.kb import KbArticle
from app.models.links import ServiceLink
from app.models.news import News
from app.models.user import User
from app.schemas.kb import SearchResponse, SearchResultItem, SuggestResponse

router = APIRouter(prefix="/search", tags=["search"])

_SNIPPET_LEN = 200


def _truncate(s: str, n: int = _SNIPPET_LEN) -> str:
    return s[:n] + "…" if len(s) > n else s


@router.get(
    "",
    response_model=SearchResponse,
    summary="Глобальный поиск",
    dependencies=[Depends(RateLimiter(times=60, minutes=1))],
)
async def global_search(
    db: DbDep,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=200),
    type_filter: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    results: list[SearchResultItem] = []

    search_types = {"article", "news", "link", "user"}
    if type_filter and type_filter in search_types:
        search_types = {type_filter}

    # ── KB статьи ────────────────────────────────────────────────────────────
    if "article" in search_types:
        fts_cond = KbArticle.body_tsvector.op("@@")(
            func.plainto_tsquery("russian_hunspell", q)
        )
        trgm_cond = KbArticle.title.op("%%")(q)
        stmt = (
            select(KbArticle)
            .where(
                KbArticle.deleted_at.is_(None),
                KbArticle.status == "published",
                or_(fts_cond, trgm_cond),
            )
            .order_by(
                func.ts_rank(KbArticle.body_tsvector, func.plainto_tsquery("russian_hunspell", q)).desc()
            )
            .limit(limit)
        )
        article_rows = (await db.execute(stmt)).scalars().all()
        for a in article_rows:
            snippet_raw = a.body[:_SNIPPET_LEN * 2]
            results.append(SearchResultItem(
                type="article",
                id=str(a.id),
                title=a.title,
                snippet=_truncate(snippet_raw.replace("\n", " ")),
                url=f"/kb/articles/{a.id}",
                created_at=a.created_at,
            ))

    # ── Новости ───────────────────────────────────────────────────────────────
    if "news" in search_types:
        fts_cond = News.body_tsvector.op("@@")(
            func.plainto_tsquery("russian_hunspell", q)
        )
        trgm_cond = News.title.op("%%")(q)
        news_stmt = (
            select(News)
            .where(
                News.deleted_at.is_(None),
                News.status == "published",
                or_(
                    (News.target_departments.is_(None)),
                    (News.target_departments.op("@>")(
                        text(f"ARRAY['{user.department}']::text[]") if user.department else text("ARRAY[]::text[]")
                    )),
                ),
                or_(fts_cond, trgm_cond),
            )
            .order_by(
                func.ts_rank(News.body_tsvector, func.plainto_tsquery("russian_hunspell", q)).desc()
            )
            .limit(limit)
        )
        news_rows = (await db.execute(news_stmt)).scalars().all()
        for n in news_rows:
            results.append(SearchResultItem(
                type="news",
                id=str(n.id),
                title=n.title,
                snippet=_truncate(n.body.replace("\n", " ")),
                url=f"/news/{n.id}",
                created_at=n.created_at,
            ))

    # ── Ярлыки ────────────────────────────────────────────────────────────────
    if "link" in search_types:
        link_stmt = (
            select(ServiceLink)
            .where(
                ServiceLink.is_active.is_(True),
                or_(
                    ServiceLink.title.ilike(f"%{q}%"),
                    ServiceLink.description.ilike(f"%{q}%"),
                ),
            )
            .limit(limit)
        )
        link_rows = (await db.execute(link_stmt)).scalars().all()
        for lnk in link_rows:
            results.append(SearchResultItem(
                type="link",
                id=str(lnk.id),
                title=lnk.title,
                snippet=lnk.description,
                url=lnk.url,
                created_at=lnk.created_at,
            ))

    # ── Пользователи ──────────────────────────────────────────────────────────
    if "user" in search_types:
        user_stmt = (
            select(User)
            .where(
                or_(
                    User.full_name.ilike(f"%{q}%"),
                    User.email.ilike(f"%{q}%"),
                    User.department.ilike(f"%{q}%"),
                    User.position.ilike(f"%{q}%"),
                )
            )
            .limit(limit)
        )
        user_rows = (await db.execute(user_stmt)).scalars().all()
        for u in user_rows:
            results.append(SearchResultItem(
                type="user",
                id=str(u.id),
                title=u.full_name,
                snippet=f"{u.position or ''} · {u.department or ''}".strip(" ·"),
                url=f"/users/{u.id}",
                created_at=u.created_at,
            ))

    results.sort(key=lambda r: r.created_at or datetime.min, reverse=True)

    paged = results[offset: offset + limit]

    return SearchResponse(items=paged, total=None, query=q)


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    summary="Typeahead подсказки",
    dependencies=[Depends(RateLimiter(times=120, minutes=1))],
)
async def search_suggest(
    db: DbDep,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=100),
) -> SuggestResponse:
    suggestions: list[str] = []

    article_r = await db.execute(
        select(KbArticle.title)
        .where(
            KbArticle.deleted_at.is_(None),
            KbArticle.status == "published",
            KbArticle.title.op("%%")(q),
        )
        .order_by(func.similarity(KbArticle.title, q).desc())
        .limit(5)
    )
    for (title,) in article_r:
        suggestions.append(title)

    news_r = await db.execute(
        select(News.title)
        .where(
            News.deleted_at.is_(None),
            News.status == "published",
            News.title.op("%%")(q),
        )
        .order_by(func.similarity(News.title, q).desc())
        .limit(5)
    )
    for (title,) in news_r:
        if title not in suggestions:
            suggestions.append(title)

    return SuggestResponse(suggestions=suggestions[:10])
