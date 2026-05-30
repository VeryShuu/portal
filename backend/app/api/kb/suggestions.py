"""KB suggestions (edit proposals) endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.models.kb import KbArticle, KbSuggestion
from app.models.user import User
from app.schemas.kb import (
    CreateSuggestionRequest,
    KbSuggestionPublic,
    KbUserRef,
    ReviewSuggestionRequest,
    ReviewSuggestionResponse,
    SuggestionListResponse,
    SuggestionResponse,
)
from app.services.kb_acl import require_article_permission
from app.services.notifications import notify_suggestion_reviewed

from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
logger = get_logger(__name__)


@router.post(
    "/articles/{article_id}/suggest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuggestionResponse,
    summary="Предложить правку",
)
async def suggest_edit(
    article_id: uuid.UUID,
    body: CreateSuggestionRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> SuggestionResponse:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)
    suggestion = KbSuggestion(
        article_id=article_id,
        author_id=user.id,
        body=body.body,
        comment=body.comment,
        status="pending",
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    logger.info(
        "kb.suggestion_created",
        article_id=str(article_id),
        suggestion_id=str(suggestion.id),
        user_id=str(user.id),
    )
    return SuggestionResponse(
        suggestion_id=suggestion.id, message="Правка отправлена на рассмотрение"
    )


@router.get(
    "/articles/{article_id}/suggestions",
    response_model=SuggestionListResponse,
    summary="Список правок (editor+)",
)
async def list_suggestions(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> SuggestionListResponse:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)
    result = await db.execute(
        select(KbSuggestion)
        .where(KbSuggestion.article_id == article_id)
        .order_by(KbSuggestion.created_at.desc())
    )
    suggestions = result.scalars().all()
    user_ids = {s.author_id for s in suggestions if s.author_id}
    users_map: dict[uuid.UUID, User] = {}
    if user_ids:
        u_r = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in u_r.scalars():
            users_map[u.id] = u

    items = []
    for s in suggestions:
        author = users_map.get(s.author_id) if s.author_id else None
        items.append(
            KbSuggestionPublic(
                id=s.id,
                article_id=s.article_id,
                body=s.body,
                comment=s.comment,
                status=s.status,
                reviewed_at=s.reviewed_at,
                created_at=s.created_at,
                author=KbUserRef(
                    id=author.id, full_name=author.full_name, avatar_url=author.avatar_url
                )
                if author
                else None,
            )
        )
    return SuggestionListResponse(items=items)


@router.post(
    "/suggestions/{suggestion_id}/review",
    response_model=ReviewSuggestionResponse,
    summary="Принять/отклонить правку (editor+)",
)
async def review_suggestion(
    suggestion_id: uuid.UUID,
    body: ReviewSuggestionRequest,
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
) -> ReviewSuggestionResponse:
    result = await db.execute(select(KbSuggestion).where(KbSuggestion.id == suggestion_id))
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    if suggestion.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already reviewed")

    article_result = await db.execute(
        select(KbArticle).where(KbArticle.id == suggestion.article_id)
    )
    article = article_result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    await require_article_permission(user, article, "editor", db, redis)

    suggestion.status = "approved" if body.action == "approve" else "rejected"
    suggestion.reviewed_by = user.id
    suggestion.reviewed_at = datetime.now(UTC)
    await db.commit()

    if article and suggestion.author_id:
        await notify_suggestion_reviewed(
            db,
            redis,
            suggestion_author_id=suggestion.author_id,
            article_id=suggestion.article_id,
            article_title=article.title,
            action=body.action,
        )
        await db.commit()

    return ReviewSuggestionResponse(status=suggestion.status)
