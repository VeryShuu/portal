"""KB tags endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models.kb import KbArticle, KbArticleTag, KbTag
from app.schemas.kb import KbTagPublic

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/tags", response_model=list[KbTagPublic], summary="Список тегов KB")
async def list_tags(
    db: DbDep,
    user: CurrentUser,
) -> list[KbTagPublic]:
    result = await db.execute(
        select(KbTag)
        .where(
            KbTag.id.in_(
                select(KbArticleTag.tag_id)
                .join(KbArticle, KbArticle.id == KbArticleTag.article_id)
                .where(KbArticle.deleted_at.is_(None))
                .distinct()
            )
        )
        .order_by(KbTag.name)
    )
    return [KbTagPublic.model_validate(t) for t in result.scalars()]
