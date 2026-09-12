"""KB articles CRUD endpoints (create / read / update / save_draft)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Header, HTTPException, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.api.kb import articles as _articles
from app.core.constants import IDEMPOTENCY_TTL, PERM_EDITOR, PERM_MANAGER
from app.schemas.kb import (
    CreateArticleRequest,
    DraftSaveRequest,
    KbArticlePublic,
    UpdateArticleRequest,
)

from . import _repo

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post(
    "/articles",
    status_code=status.HTTP_201_CREATED,
    response_model=KbArticlePublic,
    summary="Создать статью",
)
async def create_article(
    body: CreateArticleRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> KbArticlePublic:
    if idempotency_key:
        cached = await redis.get(f"idem:kb_article:{user.id}:{idempotency_key}")
        if cached:
            return cast(KbArticlePublic, KbArticlePublic.model_validate_json(cached))

    if body.status not in ("draft", "published"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )

    if body.section_id is not None:
        sec = await _repo.get_active_section(db, body.section_id)
        if not sec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        await _articles.require_section_permission(user, sec, PERM_EDITOR, db, redis)

    article = _articles.KbArticle(
        section_id=body.section_id,
        title=_articles.clean_title(body.title),
        body=_articles.sanitize_markdown(body.body) if body.body else body.body,
        status=body.status,
        version=1,
        created_by=user.id,
        updated_by=user.id,
        published_at=datetime.now(UTC) if body.status == "published" else None,
    )
    db.add(article)
    await db.flush()

    if body.tags:
        await _articles.set_article_tags(db, article, body.tags)

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _articles._get_breadcrumbs(db, article.section_id)
    await _articles._emit_audit(
        redis,
        event_type="kb.article_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article.id),
        resource_title=article.title,
    )
    result = _articles._article_to_public(
        article, breadcrumbs, user, user, user_permission=PERM_MANAGER
    )
    if idempotency_key:
        await redis.set(
            f"idem:kb_article:{user.id}:{idempotency_key}",
            result.model_dump_json(),
            ex=IDEMPOTENCY_TTL,
        )
    return result


@router.get("/articles/{article_id}", response_model=KbArticlePublic, summary="Получить статью")
async def get_article(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbArticlePublic:
    article = await _articles._get_article_or_404(db, article_id)

    user_perm = await _articles.resolve_article_permission(user, article, db, redis)
    if user_perm is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient KB permissions"
        )
    if article.status != "published" and user_perm not in (PERM_EDITOR, PERM_MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await _articles.record_article_view(db, redis, article_id, user.id)
    await db.refresh(article, attribute_names=["view_count"])

    users_map = await _articles.build_users_map(db, {article.created_by, article.updated_by})
    creator = users_map.get(article.created_by) if article.created_by else None
    updater = users_map.get(article.updated_by) if article.updated_by else creator
    if not updater:
        updater = creator

    fb = await _repo.get_feedback_summary(db, article_id=article_id, user_id=user.id)
    user_feedback = None if fb.user_fb is None else bool(fb.user_fb)

    breadcrumbs = await _articles._get_breadcrumbs(db, article.section_id)
    return _articles._article_to_public(
        article,
        breadcrumbs,
        creator,
        updater,
        helpful=fb.helpful,
        not_helpful=fb.not_helpful,
        user_feedback=user_feedback,
        user_permission=user_perm,
    )


@router.put("/articles/{article_id}", response_model=KbArticlePublic, summary="Обновить статью")
async def update_article(
    article_id: uuid.UUID,
    body: UpdateArticleRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbArticlePublic:
    article = await _repo.get_article_for_update(db, article_id)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    await _articles.require_article_permission(user, article, PERM_EDITOR, db, redis)

    if article.version != body.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Статья изменена другим пользователем",
            headers={
                "X-Current-Version": str(article.version),
                "X-Your-Version": str(body.version),
            },
        )

    if (
        "section_id" in body.model_fields_set
        and body.section_id != article.section_id
        and body.section_id is not None
    ):
        new_sec = await _repo.get_active_section(db, body.section_id)
        if not new_sec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        await _articles.require_section_permission(user, new_sec, PERM_EDITOR, db, redis)

    version_snapshot = _articles.KbArticleVersion(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment=body.change_comment,
    )
    db.add(version_snapshot)

    update_values: dict = {
        "version": _articles.KbArticle.version + 1,
        "updated_by": user.id,
        "updated_at": datetime.now(UTC),
    }
    if body.title is not None:
        update_values["title"] = _articles.clean_title(body.title)
    if body.body is not None:
        update_values["body"] = _articles.sanitize_markdown(body.body)
    if "section_id" in body.model_fields_set:
        update_values["section_id"] = body.section_id
    if body.status is not None:
        if body.status not in ("draft", "published", "archived"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
            )
        if body.status == "published" and article.published_at is None:
            update_values["published_at"] = datetime.now(UTC)
        update_values["status"] = body.status

    updated = await _repo.apply_article_update(
        db,
        article_id=article_id,
        expected_version=body.version,
        values=update_values,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Статья изменена другим пользователем",
            headers={
                "X-Current-Version": str(article.version),
                "X-Your-Version": str(body.version),
            },
        )

    if body.tags is not None:
        await _articles.set_article_tags(db, article, body.tags)

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _articles._get_breadcrumbs(db, article.section_id)
    users_map = await _articles.build_users_map(
        db, {article.created_by} if article.created_by else set()
    )
    creator = users_map.get(article.created_by) if article.created_by else None
    await _articles._emit_audit(
        redis,
        event_type="kb.article_updated",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article.id),
        resource_title=article.title,
    )
    return _articles._article_to_public(article, breadcrumbs, creator, user)


@router.put(
    "/articles/{article_id}/draft",
    response_model=KbArticlePublic,
    summary="Автосохранение черновика",
)
async def save_draft(
    article_id: uuid.UUID,
    body: DraftSaveRequest,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbArticlePublic:
    article = await _repo.get_article_for_update(db, article_id)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    await _articles.require_article_permission(user, article, PERM_EDITOR, db, redis)

    if article.version != body.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Статья изменена другим пользователем",
            headers={
                "X-Current-Version": str(article.version),
                "X-Your-Version": str(body.version),
            },
        )

    if article.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only drafts can be auto-saved this way"
        )

    version_snapshot = _articles.KbArticleVersion(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment="Auto-saved draft",
    )
    db.add(version_snapshot)

    if body.title is not None:
        article.title = _articles.clean_title(body.title)
    if body.body is not None:
        article.body = _articles.sanitize_markdown(body.body)
    article.version = article.version + 1
    article.updated_at = datetime.now(UTC)
    article.updated_by = user.id

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _articles._get_breadcrumbs(db, article.section_id)
    users_map = await _articles.build_users_map(
        db, {article.created_by} if article.created_by else set()
    )
    creator = users_map.get(article.created_by) if article.created_by else None
    return _articles._article_to_public(article, breadcrumbs, creator, user)
