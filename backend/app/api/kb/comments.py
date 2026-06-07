"""KB article comments endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.sanitize import sanitize_markdown
from app.models.kb import KbArticleComment
from app.schemas.kb import (
    CreateCommentRequest,
    KbCommentList,
    KbCommentPublic,
    KbUserRef,
)
from app.services.kb_acl import require_article_permission

from . import comments_repo
from ._common import _get_article_or_404

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get(
    "/articles/{article_id}/comments", response_model=KbCommentList, summary="Комментарии статьи"
)
async def list_comments(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> KbCommentList:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    total = await comments_repo.count_comments(db, article_id)
    comments = await comments_repo.list_comments(db, article_id, limit=limit, offset=offset)

    user_ids = {c.author_id for c in comments if c.author_id}
    users_map = await comments_repo.get_comment_authors(db, user_ids)

    items = []
    for c in comments:
        author = users_map.get(c.author_id) if c.author_id else None
        items.append(
            KbCommentPublic(
                id=c.id,
                article_id=c.article_id,
                body=None if c.deleted_at else c.body,
                is_deleted=c.deleted_at is not None,
                created_at=c.created_at,
                updated_at=c.updated_at,
                author=KbUserRef(
                    id=author.id, full_name=author.full_name, avatar_url=author.avatar_url
                )
                if author and not c.deleted_at
                else None,
            )
        )

    return KbCommentList(items=items, total=total)


@router.post(
    "/articles/{article_id}/comments",
    status_code=status.HTTP_201_CREATED,
    response_model=KbCommentPublic,
    summary="Добавить комментарий",
)
async def create_comment(
    article_id: uuid.UUID,
    body: CreateCommentRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbCommentPublic:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    comment = KbArticleComment(
        article_id=article_id,
        author_id=user.id,
        body=sanitize_markdown(body.body),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return KbCommentPublic(
        id=comment.id,
        article_id=comment.article_id,
        body=comment.body,
        is_deleted=False,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        author=KbUserRef(id=user.id, full_name=user.full_name, avatar_url=user.avatar_url),
    )


@router.delete(
    "/articles/{article_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить комментарий",
)
async def delete_comment(
    article_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
) -> None:
    comment = await comments_repo.get_comment(
        db, article_id=article_id, comment_id=comment_id
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.deleted_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already deleted")
    if user.role != "admin" and comment.author_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    comment.deleted_at = datetime.now(UTC)
    await db.commit()
