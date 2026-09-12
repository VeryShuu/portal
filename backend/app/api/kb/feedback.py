"""KB article feedback (helpful/not helpful) endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.kb import KbArticleFeedback
from app.schemas.kb import FeedbackRequest, FeedbackStats
from app.services.kb_acl import require_article_permission

from . import feedback_repo
from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post(
    "/articles/{article_id}/feedback",
    response_model=FeedbackStats,
    summary="Оценить статью (полезна/нет)",
)
async def submit_feedback(
    article_id: uuid.UUID,
    body: FeedbackRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> FeedbackStats:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    fb = await feedback_repo.get_user_feedback(db, article_id=article_id, user_id=user.id)
    if fb:
        fb.is_helpful = body.is_helpful
    else:
        fb = KbArticleFeedback(article_id=article_id, user_id=user.id, is_helpful=body.is_helpful)
        db.add(fb)
    await db.commit()

    return FeedbackStats(
        helpful_count=await feedback_repo.count_feedback(db, article_id, is_helpful=True),
        not_helpful_count=await feedback_repo.count_feedback(db, article_id, is_helpful=False),
        user_feedback=body.is_helpful,
    )
