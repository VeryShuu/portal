"""GET /kb/articles — список статей KB с фильтрами и поиском."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.kb import articles as _articles
from app.schemas.kb import KbArticleList, KbArticleListItem, KbTagPublic
from app.services.kb_tree import KB_SECTIONS_DESCENDANTS_SQL

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/articles", response_model=KbArticleList, summary="Список статей KB")
async def list_articles(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    section_id: uuid.UUID | None = Query(default=None),
    tag: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> KbArticleList:
    stmt = (
        select(_articles.KbArticle)
        .options(selectinload(_articles.KbArticle.tags))
        .where(_articles.KbArticle.deleted_at.is_(None))
        .order_by(func.lower(_articles.KbArticle.title).asc())
    )

    if not status_filter:
        if user.role != "admin":
            stmt = stmt.where(
                (_articles.KbArticle.status == "published")
                | (_articles.KbArticle.created_by == user.id)
            )
    else:
        stmt = stmt.where(_articles.KbArticle.status == status_filter)

    if section_id:
        descendants_result = await db.execute(
            text(KB_SECTIONS_DESCENDANTS_SQL),
            {"section_id": str(section_id)},
        )
        section_ids = [row[0] for row in descendants_result.fetchall()]
        if not section_ids:
            return KbArticleList(items=[], total=0, limit=limit, offset=offset)
        stmt = stmt.where(_articles.KbArticle.section_id.in_(section_ids))

    if tag:
        tag_result = await db.execute(
            select(_articles.KbTag).where(_articles.KbTag.slug == _articles._slugify(tag))
        )
        tag_obj = tag_result.scalar_one_or_none()
        if tag_obj:
            stmt = stmt.join(
                _articles.KbArticleTag,
                _articles.KbArticleTag.article_id == _articles.KbArticle.id,
            ).where(_articles.KbArticleTag.tag_id == tag_obj.id)
        else:
            return KbArticleList(items=[], total=0, limit=limit, offset=offset)

    if q:
        q_trimmed = q.strip()
        if q_trimmed:
            like_pattern = f"%{q_trimmed}%"
            prefix_pattern = f"{q_trimmed}%"
            title_lower = func.lower(_articles.KbArticle.title)
            needle_lower = func.lower(q_trimmed)
            stmt = stmt.where(
                title_lower.like(func.lower(like_pattern))
                | _articles.KbArticle.body_tsvector.op("@@")(
                    func.websearch_to_tsquery("russian_hunspell", q_trimmed)
                )
            )
            rank_expr = case(
                (title_lower == needle_lower, 0),
                (title_lower.like(func.lower(prefix_pattern)), 1),
                (title_lower.like(func.lower(like_pattern)), 2),
                else_=3,
            )
            stmt = stmt.order_by(
                rank_expr.asc(), func.lower(_articles.KbArticle.title).asc()
            )

    stmt = await _articles.apply_article_visibility(stmt, user, db)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(stmt.limit(limit).offset(offset))
    articles = result.scalars().all()

    creators = await _articles.build_users_map(
        db, {a.created_by for a in articles if a.created_by}
    )

    items = []
    for a in articles:
        creator = creators.get(a.created_by) if a.created_by else None
        items.append(
            KbArticleListItem(
                id=a.id,
                title=a.title,
                section_id=a.section_id,
                status=a.status,
                version=a.version,
                view_count=a.view_count,
                published_at=a.published_at,
                created_at=a.created_at,
                updated_at=a.updated_at,
                tags=[KbTagPublic(id=t.id, name=t.name, slug=t.slug) for t in (a.tags or [])],
                created_by=_articles.user_ref(creator),
            )
        )

    return KbArticleList(items=items, total=total, limit=limit, offset=offset)
