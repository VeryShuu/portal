"""KB articles delete / purge / restore endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.api.kb import articles as _articles
from app.schemas.kb import KbArticlePublic

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить статью (soft)",
)
async def delete_article(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> None:
    article = await _articles._get_article_or_404(db, article_id)
    if user.role != "admin" and article.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this article",
        )
    article.deleted_at = datetime.now(UTC)
    article.updated_by = user.id
    await db.commit()
    await _articles.push_audit_event(
        redis,
        event_type="kb.article_deleted",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
        resource_id=str(article_id),
    )


@router.post(
    "/articles/{article_id}/purge",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Окончательно удалить статью вместе с файлами",
)
async def purge_article_endpoint(
    article_id: uuid.UUID,
    db: DbDep,
    user: AdminDep,
    redis: RedisDep,
) -> None:
    removed = await _articles.purge_article(db, article_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    await _articles.push_audit_event(
        redis,
        event_type="kb.article_purged",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
        resource_id=str(article_id),
    )


@router.post(
    "/articles/{article_id}/restore", response_model=KbArticlePublic, summary="Восстановить статью"
)
async def restore_article(
    article_id: uuid.UUID,
    db: DbDep,
    user: AdminDep,
) -> KbArticlePublic:
    result = await db.execute(
        select(_articles.KbArticle)
        .options(selectinload(_articles.KbArticle.tags))
        .where(_articles.KbArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.deleted_at = None
    await db.commit()
    await db.refresh(article)
    breadcrumbs = await _articles._get_breadcrumbs(db, article.section_id)
    return _articles._article_to_public(article, breadcrumbs, None, None)
