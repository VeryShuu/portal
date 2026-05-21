"""News poll API: multi-question polls with optional questions and free-form answers."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.news import News as NewsModel
from app.models.user import User
from app.schemas.news_poll import (
    CreateNewsPollRequest,
    NewsPollPublic,
    NewsPollVoteRequest,
    UpdateNewsPollRequest,
)
from app.services import news as news_svc

from ._common import emit_news_audit, require_news_read_access

router = APIRouter(prefix="/{news_id}/poll")


PRIVILEGED_ROLES = ("editor", "admin")


def _poll_title(poll: Any) -> str:
    """Best-effort short title for audit logs (first question text)."""
    questions = getattr(poll, "questions", None) or []
    if questions:
        first = sorted(questions, key=lambda q: q.sort_order)[0]
        return first.text or ""
    return ""


async def _get_news_or_404(db: DbDep, news_id: uuid.UUID) -> NewsModel:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return news


async def news_for_read(news_id: uuid.UUID, db: DbDep, user: CurrentUser) -> NewsModel:
    """Resolve news and ensure the caller may read it (used by GET / vote routes)."""
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)
    return news


async def news_for_manage(news_id: uuid.UUID, db: DbDep, user: CurrentUser) -> NewsModel:
    """Resolve news and ensure the caller may manage its poll (editors/admins only)."""
    news = await _get_news_or_404(db, news_id)
    if user.role not in PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only editors and administrators can manage polls",
        )
    return news


NewsForRead = Annotated[NewsModel, Depends(news_for_read)]
NewsForManage = Annotated[NewsModel, Depends(news_for_manage)]


async def _audit_poll(
    redis: RedisDep,
    *,
    event_type: str,
    actor: User,
    request: Request,
    poll_id: uuid.UUID,
    title: str,
) -> None:
    await emit_news_audit(
        redis,
        event_type=event_type,
        actor=actor,
        request=request,
        resource_id=str(poll_id),
        resource_title=title,
    )


@router.post(
    "",
    response_model=NewsPollPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать опрос для новости",
)
async def create_news_poll(
    news_id: uuid.UUID,
    body: CreateNewsPollRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    _news: NewsForManage,
) -> NewsPollPublic:
    poll = await news_svc.create_poll(db, news_id, body)
    await _audit_poll(
        redis,
        event_type="poll.created",
        actor=user,
        request=request,
        poll_id=poll.id,
        title=_poll_title(poll),
    )
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.get("", response_model=NewsPollPublic, summary="Получить опрос новости")
async def get_news_poll(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    _news: NewsForRead,
) -> NewsPollPublic:
    poll = await news_svc.get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.patch("", response_model=NewsPollPublic, summary="Обновить опрос")
async def patch_news_poll(
    news_id: uuid.UUID,
    body: UpdateNewsPollRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    _news: NewsForManage,
) -> NewsPollPublic:
    poll = await news_svc.update_poll(db, news_id, body)
    await _audit_poll(
        redis,
        event_type="poll.updated",
        actor=user,
        request=request,
        poll_id=poll.id,
        title=_poll_title(poll),
    )
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить опрос")
async def delete_news_poll(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    _news: NewsForManage,
) -> None:
    poll = await news_svc.get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    title = _poll_title(poll)
    poll_id = poll.id
    await news_svc.delete_poll(db, news_id)
    await _audit_poll(
        redis,
        event_type="poll.deleted",
        actor=user,
        request=request,
        poll_id=poll_id,
        title=title,
    )


@router.post("/close", response_model=NewsPollPublic, summary="Принудительно закрыть опрос")
async def close_news_poll(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    _news: NewsForManage,
) -> NewsPollPublic:
    poll = await news_svc.close_poll(db, news_id, datetime.now(UTC))
    await _audit_poll(
        redis,
        event_type="poll.closed",
        actor=user,
        request=request,
        poll_id=poll.id,
        title=_poll_title(poll),
    )
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.post("/reopen", response_model=NewsPollPublic, summary="Переоткрыть опрос")
async def reopen_news_poll(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    _news: NewsForManage,
) -> NewsPollPublic:
    poll = await news_svc.reopen_poll(db, news_id, datetime.now(UTC))
    await _audit_poll(
        redis,
        event_type="poll.reopened",
        actor=user,
        request=request,
        poll_id=poll.id,
        title=_poll_title(poll),
    )
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.post("/vote", response_model=NewsPollPublic, summary="Проголосовать")
async def vote_in_news_poll(
    news_id: uuid.UUID,
    body: NewsPollVoteRequest,
    user: CurrentUser,
    db: DbDep,
    _news: NewsForRead,
) -> NewsPollPublic:
    await news_svc.cast_vote(db, news_id, user.id, body.answers, datetime.now(UTC))
    poll = await news_svc.get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.delete("/vote", response_model=NewsPollPublic, summary="Отозвать свой голос")
async def revoke_vote_in_news_poll(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    _news: NewsForRead,
) -> NewsPollPublic:
    await news_svc.revoke_vote(db, news_id, user.id, datetime.now(UTC))
    poll = await news_svc.get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    return await news_svc.build_poll_public_response(db, poll, user, datetime.now(UTC))


@router.get("/voters", summary="Получить список проголосовавших")
async def list_poll_voters(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    _news: NewsForRead,
) -> list[dict[str, Any]]:
    return await news_svc.get_voters_list(db, news_id, user=user, now=datetime.now(UTC))
