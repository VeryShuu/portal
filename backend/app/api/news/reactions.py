"""News reactions (likes) endpoints.

Лайк — toggle: ``POST`` ставит, ``DELETE`` снимает. Идемпотентно (повторный
вызов не плодит строки и не двигает счётчик). Доступ — любой авторизованный с
read-доступом к новости (см. ``require_news_read_access``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbDep
from app.schemas.news import NewsLikeState
from app.services import news as news_svc

from ._common import require_news_read_access

router = APIRouter()


async def _get_news_or_404(db: DbDep, news_id: uuid.UUID):  # type: ignore[no-untyped-def]
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return news


@router.post("/{news_id}/like", response_model=NewsLikeState, summary="Поставить лайк новости")
async def like_news(news_id: uuid.UUID, user: CurrentUser, db: DbDep) -> NewsLikeState:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)
    return await news_svc.like_news(db, news_id=news_id, user_id=user.id)


@router.delete("/{news_id}/like", response_model=NewsLikeState, summary="Снять лайк с новости")
async def unlike_news(news_id: uuid.UUID, user: CurrentUser, db: DbDep) -> NewsLikeState:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)
    return await news_svc.unlike_news(db, news_id=news_id, user_id=user.id)
