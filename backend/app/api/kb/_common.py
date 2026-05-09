"""Shared helpers for the KB API package."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.text import slugify as _slugify_common
from app.models.kb import KbArticle
from app.models.user import User
from app.schemas.kb import KbArticlePublic, KbBreadcrumb, KbTagPublic, KbUserRef


def _slugify(text_: str) -> str:
    return _slugify_common(text_, fallback="section")


def _rfc5987_filename(name: str) -> str:
    encoded = quote(name, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


async def _get_breadcrumbs(db: Any, section_id: uuid.UUID | None) -> list[KbBreadcrumb]:
    if not section_id:
        return []
    result = await db.execute(
        text("""
            WITH RECURSIVE crumbs AS (
                SELECT id, parent_id, title, slug, 0 AS depth
                FROM kb_sections WHERE id = :section_id AND deleted_at IS NULL
                UNION ALL
                SELECT s.id, s.parent_id, s.title, s.slug, c.depth + 1
                FROM kb_sections s
                JOIN crumbs c ON s.id = c.parent_id
                WHERE c.depth < 10 AND s.deleted_at IS NULL
            )
            SELECT id, title, slug FROM crumbs ORDER BY depth DESC
        """),
        {"section_id": str(section_id)},
    )
    rows = result.fetchall()
    return [KbBreadcrumb(id=r[0], title=r[1], slug=r[2]) for r in rows]


async def _get_article_or_404(db: Any, article_id: uuid.UUID) -> KbArticle:
    result = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def _article_to_public(
    article: KbArticle,
    breadcrumbs: list[KbBreadcrumb],
    creator: User | None,
    updater: User | None,
    helpful: int = 0,
    not_helpful: int = 0,
    user_feedback: bool | None = None,
    user_permission: str | None = None,
) -> KbArticlePublic:
    return KbArticlePublic(
        id=article.id,
        title=article.title,
        body=article.body,
        section_id=article.section_id,
        status=article.status,
        version=article.version,
        view_count=article.view_count,
        published_at=article.published_at,
        created_at=article.created_at,
        updated_at=article.updated_at,
        tags=[KbTagPublic(id=t.id, name=t.name, slug=t.slug) for t in (article.tags or [])],
        breadcrumbs=breadcrumbs,
        created_by=KbUserRef(
            id=creator.id, full_name=creator.full_name, avatar_url=creator.avatar_url
        )
        if creator
        else None,
        updated_by=KbUserRef(
            id=updater.id, full_name=updater.full_name, avatar_url=updater.avatar_url
        )
        if updater
        else None,
        helpful_count=helpful,
        not_helpful_count=not_helpful,
        user_feedback=user_feedback,
        user_permission=user_permission,
        inherit_permissions=article.inherit_permissions,
    )



