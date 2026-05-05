"""Global Search API: FTS + pg_trgm по KB, новостям, ярлыкам, пользователям."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import String, bindparam, func, or_, select, text

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.kb import KbArticle
from app.models.links import ServiceLink
from app.models.news import News
from app.models.user import User
from app.schemas.kb import SearchResponse, SearchResultItem, SuggestResponse
from app.services.kb_acl import filter_accessible_articles

router = APIRouter(prefix="/search", tags=["search"])

_HL_OPTIONS = "MaxWords=20, MinWords=10, StartSel=**, StopSel=**"
_KB_FETCH_MULTIPLIER = 5
_DATETIME_MIN_UTC = datetime.min.replace(tzinfo=UTC)


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    q: str = Query(min_length=1, max_length=200),
    type_filter: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    author_id: UUID | None = None,
    department: str | None = None,
) -> SearchResponse:
    search_types = {"article", "news", "link", "user"}
    if type_filter and type_filter in search_types:
        search_types = {type_filter}

    single_type = len(search_types) == 1
    kb_fetch_limit = (offset + limit) * _KB_FETCH_MULTIPLIER
    multi_fetch_limit = offset + limit

    tsq_article = func.plainto_tsquery("russian_hunspell", q)
    tsq_news = func.plainto_tsquery("russian_hunspell", q)

    results: list[SearchResultItem] = []

    # ── KB статьи ────────────────────────────────────────────────────────────
    if "article" in search_types:
        fts_cond = KbArticle.body_tsvector.op("@@")(tsq_article)
        trgm_cond = KbArticle.title.op("%%")(q)
        headline_col = func.ts_headline(
            "russian_hunspell", KbArticle.body, tsq_article, _HL_OPTIONS
        ).label("headline")
        conditions = [
            KbArticle.deleted_at.is_(None),
            KbArticle.status == "published",
            or_(fts_cond, trgm_cond),
        ]
        if from_date:
            conditions.append(KbArticle.created_at >= from_date)
        if to_date:
            conditions.append(KbArticle.created_at <= to_date)
        if author_id:
            conditions.append(KbArticle.created_by == author_id)
        stmt = (
            select(KbArticle, headline_col)
            .where(*conditions)
            .order_by(func.ts_rank(KbArticle.body_tsvector, tsq_article).desc())
            .limit(kb_fetch_limit)
        )
        rows = (await db.execute(stmt)).all()
        articles = await filter_accessible_articles(user, [r[0] for r in rows], db, redis)
        accessible_ids = {a.id for a in articles}
        article_results: list[SearchResultItem] = []
        for article_obj, headline in rows:
            if article_obj.id not in accessible_ids:
                continue
            article_results.append(
                SearchResultItem(
                    type="article",
                    id=str(article_obj.id),
                    title=article_obj.title,
                    snippet=headline,
                    url=f"/kb/articles/{article_obj.id}",
                    created_at=article_obj.created_at,
                )
            )
        if single_type:
            total = len(article_results)
            return SearchResponse(
                items=article_results[offset : offset + limit], total=total, query=q
            )
        results.extend(article_results)

    # ── Новости ───────────────────────────────────────────────────────────────
    if "news" in search_types:
        fts_cond = News.body_tsvector.op("@@")(tsq_news)
        trgm_cond = News.title.op("%%")(q)
        headline_col = func.ts_headline("russian_hunspell", News.body, tsq_news, _HL_OPTIONS).label(
            "headline"
        )
        news_conditions = [
            News.deleted_at.is_(None),
            News.status == "published",
            or_(
                (News.target_departments.is_(None)),
                (
                    News.target_departments.op("@>")(
                        text("ARRAY[:user_dept]::text[]").bindparams(
                            bindparam("user_dept", value=user.department, type_=String)
                        )
                        if user.department
                        else text("ARRAY[]::text[]")
                    )
                ),
            ),
            or_(fts_cond, trgm_cond),
        ]
        if from_date:
            news_conditions.append(News.created_at >= from_date)
        if to_date:
            news_conditions.append(News.created_at <= to_date)
        if author_id:
            news_conditions.append(News.author_id == author_id)
        if department:
            news_conditions.append(
                News.target_departments.op("@>")(
                    text("ARRAY[:filter_dept]::text[]").bindparams(
                        bindparam("filter_dept", value=department, type_=String)
                    )
                )
            )
        if single_type:
            count_stmt = select(func.count()).select_from(News).where(*news_conditions)
            news_total = (await db.execute(count_stmt)).scalar_one()
            news_stmt = (
                select(News, headline_col)
                .where(*news_conditions)
                .order_by(func.ts_rank(News.body_tsvector, tsq_news).desc())
                .offset(offset)
                .limit(limit)
            )
            news_items = [
                SearchResultItem(
                    type="news",
                    id=str(n.id),
                    title=n.title,
                    snippet=headline,
                    url=f"/news/{n.id}",
                    created_at=n.created_at,
                )
                for n, headline in (await db.execute(news_stmt)).all()
            ]
            return SearchResponse(items=news_items, total=news_total, query=q)
        news_stmt = (
            select(News, headline_col)
            .where(*news_conditions)
            .order_by(func.ts_rank(News.body_tsvector, tsq_news).desc())
            .limit(multi_fetch_limit)
        )
        for n, headline in (await db.execute(news_stmt)).all():
            results.append(
                SearchResultItem(
                    type="news",
                    id=str(n.id),
                    title=n.title,
                    snippet=headline,
                    url=f"/news/{n.id}",
                    created_at=n.created_at,
                )
            )

    # ── Ярлыки ────────────────────────────────────────────────────────────────
    if "link" in search_types:
        q_esc = _escape_like(q)
        link_conditions = [
            ServiceLink.is_active.is_(True),
            or_(
                ServiceLink.title.ilike(f"%{q_esc}%", escape="\\"),
                ServiceLink.description.ilike(f"%{q_esc}%", escape="\\"),
            ),
        ]
        if single_type:
            count_stmt = select(func.count()).select_from(ServiceLink).where(*link_conditions)
            link_total = (await db.execute(count_stmt)).scalar_one()
            link_stmt = select(ServiceLink).where(*link_conditions).offset(offset).limit(limit)
            link_items = [
                SearchResultItem(
                    type="link",
                    id=str(lnk.id),
                    title=lnk.title,
                    snippet=lnk.description,
                    url=lnk.url,
                    created_at=lnk.created_at,
                )
                for lnk in (await db.execute(link_stmt)).scalars().all()
            ]
            return SearchResponse(items=link_items, total=link_total, query=q)
        link_stmt = select(ServiceLink).where(*link_conditions).limit(multi_fetch_limit)
        for lnk in (await db.execute(link_stmt)).scalars().all():
            results.append(
                SearchResultItem(
                    type="link",
                    id=str(lnk.id),
                    title=lnk.title,
                    snippet=lnk.description,
                    url=lnk.url,
                    created_at=lnk.created_at,
                )
            )

    # ── Пользователи ──────────────────────────────────────────────────────────
    if "user" in search_types:
        q_esc = _escape_like(q)
        user_conditions = [
            or_(
                User.full_name.ilike(f"%{q_esc}%", escape="\\"),
                User.email.ilike(f"%{q_esc}%", escape="\\"),
                User.department.ilike(f"%{q_esc}%", escape="\\"),
                User.position.ilike(f"%{q_esc}%", escape="\\"),
            )
        ]
        if department:
            dept_esc = _escape_like(department)
            user_conditions.append(User.department.ilike(f"%{dept_esc}%", escape="\\"))
        if single_type:
            count_stmt = select(func.count()).select_from(User).where(*user_conditions)
            user_total = (await db.execute(count_stmt)).scalar_one()
            user_stmt = select(User).where(*user_conditions).offset(offset).limit(limit)
            user_items = [
                SearchResultItem(
                    type="user",
                    id=str(u.id),
                    title=u.full_name,
                    snippet=f"{u.position or ''} · {u.department or ''}".strip(" ·"),
                    url=f"/users/{u.id}",
                    created_at=u.created_at,
                )
                for u in (await db.execute(user_stmt)).scalars().all()
            ]
            return SearchResponse(items=user_items, total=user_total, query=q)
        user_stmt = select(User).where(*user_conditions).limit(multi_fetch_limit)
        for u in (await db.execute(user_stmt)).scalars().all():
            results.append(
                SearchResultItem(
                    type="user",
                    id=str(u.id),
                    title=u.full_name,
                    snippet=f"{u.position or ''} · {u.department or ''}".strip(" ·"),
                    url=f"/users/{u.id}",
                    created_at=u.created_at,
                )
            )

    results.sort(key=lambda r: r.created_at or _DATETIME_MIN_UTC, reverse=True)

    total = len(results)
    paged = results[offset : offset + limit]

    return SearchResponse(items=paged, total=total, query=q)


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
    suggestions: list[str] = []

    article_r = await db.execute(
        select(KbArticle)
        .where(
            KbArticle.deleted_at.is_(None),
            KbArticle.status == "published",
            KbArticle.title.op("%%")(q),
        )
        .order_by(func.similarity(KbArticle.title, q).desc())
        .limit(10)
    )
    raw_articles = article_r.scalars().all()
    accessible_articles = await filter_accessible_articles(user, list(raw_articles), db, redis)
    for a in accessible_articles[:5]:
        suggestions.append(a.title)

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
