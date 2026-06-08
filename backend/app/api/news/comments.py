"""News comments — flat list, soft-delete, with edit support.

Mirror of :mod:`app.api.kb.comments` (read for anyone with news read-access;
edit only by the author; delete by the author or an admin). Adds inline edit
(``PATCH``) which KB lacks, and maintains the denormalised
``news.comment_count`` counter in the same transaction as the mutation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbDep
from app.core.sanitize import sanitize_markdown
from app.models.news import NewsComment
from app.schemas.news import (
    CreateNewsCommentRequest,
    NewsAuthor,
    NewsCommentList,
    NewsCommentPublic,
    UpdateNewsCommentRequest,
)
from app.services import news as news_svc

from . import comments_repo
from ._common import require_news_read_access

router = APIRouter()


async def _get_news_or_404(db: DbDep, news_id: uuid.UUID):  # type: ignore[no-untyped-def]
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return news


def _to_public(comment: NewsComment, author: NewsAuthor | None) -> NewsCommentPublic:
    is_deleted = comment.deleted_at is not None
    return NewsCommentPublic(
        id=comment.id,
        news_id=comment.news_id,
        body=None if is_deleted else comment.body,
        is_deleted=is_deleted,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        author=author if author and not is_deleted else None,
    )


@router.get(
    "/{news_id}/comments", response_model=NewsCommentList, summary="Комментарии новости"
)
async def list_comments(
    news_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NewsCommentList:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)

    total = await comments_repo.count_active_comments(db, news_id)
    comments = await comments_repo.list_comments(db, news_id, limit=limit, offset=offset)

    author_ids = {c.author_id for c in comments if c.author_id}
    authors = await comments_repo.get_comment_authors(db, author_ids)

    items = [
        _to_public(
            c,
            NewsAuthor.model_validate(authors[c.author_id])
            if c.author_id and c.author_id in authors
            else None,
        )
        for c in comments
    ]
    return NewsCommentList(items=items, total=total)


@router.post(
    "/{news_id}/comments",
    status_code=status.HTTP_201_CREATED,
    response_model=NewsCommentPublic,
    summary="Добавить комментарий",
)
async def create_comment(
    news_id: uuid.UUID,
    body: CreateNewsCommentRequest,
    db: DbDep,
    user: CurrentUser,
) -> NewsCommentPublic:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)

    comment = NewsComment(
        news_id=news_id,
        author_id=user.id,
        body=sanitize_markdown(body.body),
    )
    db.add(comment)
    await comments_repo.increment_comment_count(db, news_id)
    await db.commit()
    await db.refresh(comment)
    return _to_public(comment, NewsAuthor.model_validate(user))


@router.patch(
    "/{news_id}/comments/{comment_id}",
    response_model=NewsCommentPublic,
    summary="Редактировать комментарий",
)
async def update_comment(
    news_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: UpdateNewsCommentRequest,
    db: DbDep,
    user: CurrentUser,
) -> NewsCommentPublic:
    comment = await comments_repo.get_comment(db, news_id=news_id, comment_id=comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.deleted_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Comment deleted")
    if comment.author_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    comment.body = sanitize_markdown(body.body)
    comment.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(comment)
    return _to_public(comment, NewsAuthor.model_validate(user))


@router.delete(
    "/{news_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить комментарий",
)
async def delete_comment(
    news_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
) -> None:
    comment = await comments_repo.get_comment(db, news_id=news_id, comment_id=comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.deleted_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already deleted")
    if user.role != "admin" and comment.author_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    comment.deleted_at = datetime.now(UTC)
    await comments_repo.decrement_comment_count(db, news_id)
    await db.commit()
