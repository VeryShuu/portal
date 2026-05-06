"""News service — бизнес-логика."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.sanitize import sanitize_html
from app.models.news import News, NewsVersion
from app.models.user import User

logger = get_logger(__name__)


def _targeting_filter(stmt, user: User):
    """Фильтр по таргетингу: показывать новость, если ОБА условия:
    - target_departments пуст ИЛИ содержит отдел пользователя
    - target_roles пуст ИЛИ содержит роль пользователя (P0-11)
    """
    from sqlalchemy import String, cast, or_
    from sqlalchemy.dialects.postgresql import ARRAY

    dept_clause = or_(
        News.target_departments.is_(None),
        News.target_departments == [],
    )
    if user.department is not None:
        dept_clause = or_(
            dept_clause,
            News.target_departments.contains(cast([user.department], ARRAY(String))),
        )

    role_clause = or_(
        News.target_roles.is_(None),
        News.target_roles == [],
        News.target_roles.contains(cast([user.role], ARRAY(String))),
    )

    return stmt.where(dept_clause).where(role_clause)


async def get_news_list(
    db: AsyncSession,
    *,
    user: User,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    pinned_first: bool = True,
    category: str | None = None,
    is_pinned: bool | None = None,
) -> tuple[list[News], int]:
    stmt = select(News).where(News.deleted_at.is_(None))

    if status_filter:
        stmt = stmt.where(News.status == status_filter)
    elif user.role not in ("editor", "admin"):
        stmt = stmt.where(News.status == "published")

    if category is not None:
        from sqlalchemy import String, cast
        from sqlalchemy.dialects.postgresql import ARRAY
        stmt = stmt.where(News.categories.contains(cast([category], ARRAY(String))))

    if is_pinned is not None:
        stmt = stmt.where(News.is_pinned == is_pinned)

    if user.role not in ("editor", "admin"):
        stmt = _targeting_filter(stmt, user)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    if pinned_first:
        stmt = stmt.order_by(
            News.is_pinned.desc(),
            News.published_at.desc(),
            News.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(News.published_at.desc(), News.created_at.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_news_by_id(db: AsyncSession, news_id: uuid.UUID) -> News | None:
    result = await db.execute(select(News).where(News.id == news_id, News.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def create_news(db: AsyncSession, *, author: User, data: dict) -> News:
    now = datetime.now(UTC)
    # P0-2: sanitize HTML body before persisting (XSS prevention).
    body = sanitize_html(data.get("body", ""))
    news = News(
        title=data["title"],
        body=body,
        status=data.get("status", "draft"),
        is_pinned=data.get("is_pinned", False),
        categories=data.get("categories", []),
        target_departments=data.get("target_departments"),
        target_roles=data.get("target_roles"),
        publish_at=data.get("publish_at"),
        archive_at=data.get("archive_at"),
        cover_focal_point=data.get("cover_focal_point"),
        author_id=author.id,
        current_version=1,
    )
    if news.status == "published" and not news.published_at:
        news.published_at = now

    db.add(news)
    await db.flush()

    version = NewsVersion(
        news_id=news.id,
        version=1,
        title=news.title,
        body=news.body,
        editor_id=author.id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(news)
    return news


async def update_news(db: AsyncSession, *, news: News, editor: User, data: dict) -> News:
    now = datetime.now(UTC)
    changed = False

    for field in (
        "title",
        "body",
        "status",
        "is_pinned",
        "categories",
        "target_departments",
        "target_roles",
        "publish_at",
        "archive_at",
        "published_at",
        "cover_focal_point",
    ):
        if field in data and data[field] is not None:
            new_val = data[field]
            # P0-2: sanitize body on update too.
            if field == "body":
                new_val = sanitize_html(new_val)
            if getattr(news, field) != new_val:
                setattr(news, field, new_val)
                changed = True

    if data.get("status") == "published" and not news.published_at:
        news.published_at = now

    if changed:
        news.current_version += 1
        news.updated_at = now

        version = NewsVersion(
            news_id=news.id,
            version=news.current_version,
            title=news.title,
            body=news.body,
            editor_id=editor.id,
        )
        db.add(version)
        db.add(news)
        await db.commit()
        await db.refresh(news)
    return news


async def delete_news(db: AsyncSession, news: News) -> None:
    news.deleted_at = datetime.now(UTC)
    news.status = "archived"
    await db.commit()


async def get_news_versions(db: AsyncSession, news_id: uuid.UUID) -> list[NewsVersion]:
    result = await db.execute(
        select(NewsVersion)
        .where(NewsVersion.news_id == news_id)
        .order_by(NewsVersion.version.desc())
    )
    return list(result.scalars().all())


async def increment_view_count(db: AsyncSession, news_id: uuid.UUID) -> None:
    await db.execute(update(News).where(News.id == news_id).values(view_count=News.view_count + 1))
    await db.commit()
