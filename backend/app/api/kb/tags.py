"""KB tags endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.schemas.kb import KbTagPublic

from . import tags_repo

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/tags", response_model=list[KbTagPublic], summary="Список тегов KB")
async def list_tags(
    db: DbDep,
    user: CurrentUser,
) -> list[KbTagPublic]:
    tags = await tags_repo.list_active_tags(db)
    return [KbTagPublic.model_validate(t) for t in tags]
