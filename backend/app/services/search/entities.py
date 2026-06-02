"""Per-entity search queries: build conditions, count, fetch, map to items.

Each function owns one entity (article/news/link/user), returns
``(total, items)``, and serves both the single-type (rank-ordered, paginated)
and multi-type (recency-ordered, windowed) call sites via parameters.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticle
from app.models.links import ServiceLink
from app.models.news import News
from app.models.user import User
from app.schemas.kb import SearchResultItem
from app.services.kb_acl import apply_article_visibility
from app.services.search.filters import (
    HL_OPTIONS,
    article_conditions,
    link_conditions,
    news_conditions,
    user_conditions,
)


async def search_articles(
    sess: AsyncSession,
    *,
    q: str,
    user: User,
    from_date: datetime | None,
    to_date: datetime | None,
    author_id: UUID | None,
    limit: int,
    offset: int,
    rank_order: bool,
) -> tuple[int, list[SearchResultItem]]:
    """Search published KB articles, applying ACL visibility to count and page."""
    tsq = func.plainto_tsquery("russian_hunspell", q)
    conditions = article_conditions(
        q, tsq, from_date=from_date, to_date=to_date, author_id=author_id
    )
    headline_col = func.ts_headline("russian_hunspell", KbArticle.body, tsq, HL_OPTIONS).label(
        "headline"
    )
    count_base = await apply_article_visibility(select(KbArticle).where(*conditions), user, sess)
    count_stmt = select(func.count()).select_from(count_base.subquery())
    total: int = (await sess.execute(count_stmt)).scalar_one()
    order_col = (
        func.ts_rank(KbArticle.body_tsvector, tsq).desc()
        if rank_order
        else KbArticle.created_at.desc()
    )
    page_stmt = (
        select(KbArticle, headline_col)
        .where(*conditions)
        .order_by(order_col)
        .offset(offset)
        .limit(limit)
    )
    page_stmt = await apply_article_visibility(page_stmt, user, sess)
    items = [
        SearchResultItem(
            type="article",
            id=str(article_obj.id),
            title=article_obj.title,
            snippet=headline,
            url=f"/kb/articles/{article_obj.id}",
            created_at=article_obj.created_at,
        )
        for article_obj, headline in (await sess.execute(page_stmt)).all()
    ]
    return total, items


async def search_news(
    sess: AsyncSession,
    *,
    q: str,
    user: User,
    from_date: datetime | None,
    to_date: datetime | None,
    author_id: UUID | None,
    department: str | None,
    limit: int,
    offset: int,
    rank_order: bool,
) -> tuple[int, list[SearchResultItem]]:
    """Search published news with role-targeting and optional filters."""
    tsq = func.plainto_tsquery("russian_hunspell", q)
    conditions = news_conditions(
        q,
        tsq,
        user,
        from_date=from_date,
        to_date=to_date,
        author_id=author_id,
        department=department,
    )
    headline_col = func.ts_headline("russian_hunspell", News.body, tsq, HL_OPTIONS).label(
        "headline"
    )
    count_stmt = select(func.count()).select_from(News).where(*conditions)
    total: int = (await sess.execute(count_stmt)).scalar_one()
    order_col = (
        func.ts_rank(News.body_tsvector, tsq).desc() if rank_order else News.created_at.desc()
    )
    page_stmt = (
        select(News, headline_col)
        .where(*conditions)
        .order_by(order_col)
        .offset(offset)
        .limit(limit)
    )
    items = [
        SearchResultItem(
            type="news",
            id=str(n.id),
            title=n.title,
            snippet=headline,
            url=f"/news/{n.id}",
            created_at=n.created_at,
        )
        for n, headline in (await sess.execute(page_stmt)).all()
    ]
    return total, items


async def search_links(
    sess: AsyncSession,
    *,
    q: str,
    limit: int,
    offset: int,
    ordered: bool,
) -> tuple[int, list[SearchResultItem]]:
    """Search active service links by title/description."""
    conditions = link_conditions(q)
    count_stmt = select(func.count()).select_from(ServiceLink).where(*conditions)
    total: int = (await sess.execute(count_stmt)).scalar_one()
    stmt = select(ServiceLink).where(*conditions)
    if ordered:
        stmt = stmt.order_by(ServiceLink.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    items = [
        SearchResultItem(
            type="link",
            id=str(lnk.id),
            title=lnk.title,
            snippet=lnk.description,
            url=lnk.url,
            created_at=lnk.created_at,
        )
        for lnk in (await sess.execute(stmt)).scalars().all()
    ]
    return total, items


async def search_users(
    sess: AsyncSession,
    *,
    q: str,
    department: str | None,
    limit: int,
    offset: int,
    ordered: bool,
) -> tuple[int, list[SearchResultItem]]:
    """Search users by name/email/department/position."""
    conditions = user_conditions(q, department=department)
    count_stmt = select(func.count()).select_from(User).where(*conditions)
    total: int = (await sess.execute(count_stmt)).scalar_one()
    stmt = select(User).where(*conditions)
    if ordered:
        stmt = stmt.order_by(User.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    items = [
        SearchResultItem(
            type="user",
            id=str(u.id),
            title=u.full_name,
            snippet=f"{u.position or ''} · {u.department or ''}".strip(" ·"),
            url=f"/users/{u.id}",
            created_at=u.created_at,
        )
        for u in (await sess.execute(stmt)).scalars().all()
    ]
    return total, items
