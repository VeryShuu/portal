"""CRUD-операции: list/get/create/update/delete/trash/restore/purge/versions."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.sanitize import sanitize_markdown
from app.models.news import News, NewsVersion
from app.models.user import User

from ._helpers import _NEWS_MEDIA_DIR, _targeting_filter

logger = get_logger(__name__)


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
    q: str | None = None,
    offset_override: int | None = None,
) -> tuple[list[News], int]:
    stmt: Select[Any] = (
        select(News).where(News.deleted_at.is_(None)).options(selectinload(News.poll))
    )

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

    if q:
        from sqlalchemy import or_

        pattern = f"%{q}%"
        stmt = stmt.where(or_(News.title.ilike(pattern), News.body.ilike(pattern)))

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

    effective_offset = offset_override if offset_override is not None else (page - 1) * page_size
    stmt = stmt.offset(effective_offset).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def get_news_by_id(
    db: AsyncSession, news_id: uuid.UUID, *, include_deleted: bool = False
) -> News | None:
    stmt = select(News).where(News.id == news_id).options(selectinload(News.poll))
    if not include_deleted:
        stmt = stmt.where(News.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_news(db: AsyncSession, *, author: User, data: dict) -> News:
    now = datetime.now(UTC)
    body = sanitize_markdown(data.get("body", ""))
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
        cover_focal_x=data.get("cover_focal_x"),
        cover_focal_y=data.get("cover_focal_y"),
        cover_focal_zoom=data.get("cover_focal_zoom"),
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

    nullable_fields = {"cover_focal_x", "cover_focal_y", "cover_focal_zoom"}
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
        "cover_focal_x",
        "cover_focal_y",
        "cover_focal_zoom",
    ):
        if field not in data:
            continue
        new_val = data[field]
        if new_val is None and field not in nullable_fields:
            continue
        if field == "body":
            new_val = sanitize_markdown(new_val)
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
    news.previous_status = news.status
    news.deleted_at = datetime.now(UTC)
    news.status = "archived"
    await db.commit()


async def get_trash_news(
    db: AsyncSession, *, page: int = 1, page_size: int = 20
) -> tuple[list[News], int]:
    base = select(News).where(News.deleted_at.is_not(None)).options(selectinload(News.poll))
    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_stmt)).scalar_one()
    stmt = (
        base.options(selectinload(News.author))
        .order_by(News.deleted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def restore_news(db: AsyncSession, news: News) -> News:
    news.deleted_at = None
    if news.previous_status:
        news.status = news.previous_status
        news.previous_status = None
    await db.commit()
    await db.refresh(news)
    return news


async def purge_news(db: AsyncSession, news: News) -> None:
    news_id = news.id
    shutil.rmtree(_NEWS_MEDIA_DIR / str(news_id), ignore_errors=True)
    await db.execute(
        text("DELETE FROM bookmarks WHERE resource_type='news' AND resource_id = :rid"),
        {"rid": str(news_id)},
    )
    await db.execute(delete(News).where(News.id == news_id))
    await db.commit()
    logger.info("news.purged", news_id=str(news_id))


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
