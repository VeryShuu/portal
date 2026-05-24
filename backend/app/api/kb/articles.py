"""KB articles CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import Integer, case, cast, func, select, text, update
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.constants import IDEMPOTENCY_TTL, PERM_EDITOR, PERM_MANAGER
from app.core.sanitize import clean_title, sanitize_markdown
from app.models.kb import (
    KbArticle,
    KbArticleFeedback,
    KbArticleTag,
    KbArticleVersion,
    KbSection,
    KbTag,
)
from app.models.user import User
from app.schemas.kb import (
    CreateArticleRequest,
    DraftSaveRequest,
    KbArticleList,
    KbArticleListItem,
    KbArticlePublic,
    KbTagPublic,
    KbUserRef,
    UpdateArticleRequest,
)
from app.services.audit import push_audit_event
from app.services.kb import record_article_view, set_article_tags
from app.services.kb_acl import (
    apply_article_visibility,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
)

from ._common import (
    _article_to_public,
    _get_article_or_404,
    _get_breadcrumbs,
    _slugify,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/articles", response_model=KbArticleList, summary="Список статей KB")
async def list_articles(
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    section_id: uuid.UUID | None = Query(default=None),
    tag: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> KbArticleList:
    stmt = (
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.deleted_at.is_(None))
        .order_by(KbArticle.updated_at.desc())
    )

    if not status_filter:
        if user.role != "admin":
            stmt = stmt.where(
                (KbArticle.status == "published") | (KbArticle.created_by == user.id)
            )
    else:
        stmt = stmt.where(KbArticle.status == status_filter)

    if section_id:
        descendants_result = await db.execute(
            text("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM kb_sections
                    WHERE id = :section_id AND deleted_at IS NULL
                    UNION ALL
                    SELECT s.id FROM kb_sections s
                    JOIN descendants d ON s.parent_id = d.id
                    WHERE s.deleted_at IS NULL
                )
                SELECT id FROM descendants
            """),
            {"section_id": str(section_id)},
        )
        section_ids = [row[0] for row in descendants_result.fetchall()]
        if not section_ids:
            return KbArticleList(items=[], total=0, limit=limit, offset=offset)
        stmt = stmt.where(KbArticle.section_id.in_(section_ids))

    if tag:
        tag_result = await db.execute(select(KbTag).where(KbTag.slug == _slugify(tag)))
        tag_obj = tag_result.scalar_one_or_none()
        if tag_obj:
            stmt = stmt.join(KbArticleTag, KbArticleTag.article_id == KbArticle.id).where(
                KbArticleTag.tag_id == tag_obj.id
            )
        else:
            return KbArticleList(items=[], total=0, limit=limit, offset=offset)

    if q:
        stmt = stmt.where(
            KbArticle.body_tsvector.op("@@")(func.plainto_tsquery("russian_hunspell", q))
        )

    stmt = await apply_article_visibility(stmt, user, db)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(stmt.limit(limit).offset(offset))
    articles = result.scalars().all()

    creators: dict[uuid.UUID, User] = {}
    creator_ids = {a.created_by for a in articles if a.created_by}
    if creator_ids:
        u_result = await db.execute(select(User).where(User.id.in_(creator_ids)))
        for u in u_result.scalars():
            creators[u.id] = u

    items = []
    for a in articles:
        creator = creators.get(a.created_by) if a.created_by else None
        items.append(
            KbArticleListItem(
                id=a.id,
                title=a.title,
                section_id=a.section_id,
                status=a.status,
                version=a.version,
                view_count=a.view_count,
                published_at=a.published_at,
                created_at=a.created_at,
                updated_at=a.updated_at,
                tags=[KbTagPublic(id=t.id, name=t.name, slug=t.slug) for t in (a.tags or [])],
                created_by=KbUserRef(
                    id=creator.id, full_name=creator.full_name, avatar_url=creator.avatar_url
                )
                if creator
                else None,
            )
        )

    return KbArticleList(items=items, total=total, limit=limit, offset=offset)


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
            return KbArticlePublic.model_validate_json(cached)

    if body.status not in ("draft", "published"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )

    if body.section_id is not None:
        sec_result = await db.execute(
            select(KbSection).where(KbSection.id == body.section_id, KbSection.deleted_at.is_(None))
        )
        sec = sec_result.scalar_one_or_none()
        if not sec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        await require_section_permission(user, sec, PERM_EDITOR, db, redis)

    article = KbArticle(
        section_id=body.section_id,
        title=clean_title(body.title),
        body=sanitize_markdown(body.body) if body.body else body.body,
        status=body.status,
        version=1,
        created_by=user.id,
        updated_by=user.id,
        published_at=datetime.now(UTC) if body.status == "published" else None,
    )
    db.add(article)
    await db.flush()

    if body.tags:
        await set_article_tags(db, article, body.tags)

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    await push_audit_event(
        redis,
        event_type="kb.article_created",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
        resource_id=str(article.id),
        resource_title=article.title,
    )
    result = _article_to_public(article, breadcrumbs, user, user, user_permission=PERM_MANAGER)
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
    article = await _get_article_or_404(db, article_id)

    user_perm = await resolve_article_permission(user, article, db, redis)
    if user_perm is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient KB permissions"
        )
    if article.status != "published" and user_perm not in (PERM_EDITOR, PERM_MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await record_article_view(db, redis, article_id, user.id)
    await db.refresh(article, attribute_names=["view_count"])

    user_ids = {uid for uid in (article.created_by, article.updated_by) if uid}
    users_map: dict[uuid.UUID, User] = {}
    if user_ids:
        u_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in u_result.scalars():
            users_map[u.id] = u
    creator = users_map.get(article.created_by) if article.created_by else None
    updater = users_map.get(article.updated_by) if article.updated_by else creator
    if not updater:
        updater = creator

    fb_result = await db.execute(
        select(
            func.count(1).filter(KbArticleFeedback.is_helpful.is_(True)).label("helpful"),
            func.count(1).filter(KbArticleFeedback.is_helpful.is_(False)).label("not_helpful"),
            func.max(
                case(
                    (
                        KbArticleFeedback.user_id == user.id,
                        cast(KbArticleFeedback.is_helpful, Integer),
                    ),
                    else_=None,
                )
            ).label("user_fb"),
        ).where(KbArticleFeedback.article_id == article_id)
    )
    fb = fb_result.one()
    user_feedback = None if fb.user_fb is None else bool(fb.user_fb)

    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    return _article_to_public(
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
    article_result = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
        .with_for_update()
    )
    article = article_result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    await require_article_permission(user, article, PERM_EDITOR, db, redis)

    if article.version != body.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Статья изменена другим пользователем",
            headers={
                "X-Current-Version": str(article.version),
                "X-Your-Version": str(body.version),
            },
        )

    if "section_id" in body.model_fields_set and body.section_id != article.section_id:
        if body.section_id is not None:
            sec_result = await db.execute(
                select(KbSection).where(KbSection.id == body.section_id, KbSection.deleted_at.is_(None))
            )
            new_sec = sec_result.scalar_one_or_none()
            if not new_sec:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
            await require_section_permission(user, new_sec, PERM_EDITOR, db, redis)

    version_snapshot = KbArticleVersion(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment=body.change_comment,
    )
    db.add(version_snapshot)

    update_values: dict = {
        "version": KbArticle.version + 1,
        "updated_by": user.id,
        "updated_at": datetime.now(UTC),
    }
    if body.title is not None:
        update_values["title"] = clean_title(body.title)
    if body.body is not None:
        update_values["body"] = sanitize_markdown(body.body)
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

    upd_result = await db.execute(
        update(KbArticle)
        .where(KbArticle.id == article_id, KbArticle.version == body.version)
        .values(**update_values)
        .returning(KbArticle.id)
    )
    if upd_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Статья изменена другим пользователем",
            headers={
                "X-Current-Version": str(article.version),
                "X-Your-Version": str(body.version),
            },
        )

    if body.tags is not None:
        await set_article_tags(db, article, body.tags)

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    creator = None
    if article.created_by:
        r = await db.execute(select(User).where(User.id == article.created_by))
        creator = r.scalar_one_or_none()
    await push_audit_event(
        redis,
        event_type="kb.article_updated",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
        resource_id=str(article.id),
        resource_title=article.title,
    )
    return _article_to_public(article, breadcrumbs, creator, user)


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
    article_result = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.is_(None))
        .with_for_update()
    )
    article = article_result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    await require_article_permission(user, article, PERM_EDITOR, db, redis)

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

    version_snapshot = KbArticleVersion(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment="Auto-saved draft",
    )
    db.add(version_snapshot)

    if body.title is not None:
        article.title = clean_title(body.title)
    if body.body is not None:
        article.body = sanitize_markdown(body.body)
    article.version = article.version + 1
    article.updated_at = datetime.now(UTC)
    article.updated_by = user.id

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    creator = None
    if article.created_by:
        r = await db.execute(select(User).where(User.id == article.created_by))
        creator = r.scalar_one_or_none()
    return _article_to_public(article, breadcrumbs, creator, user)


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
    article = await _get_article_or_404(db, article_id)
    if user.role != "admin" and article.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this article",
        )
    article.deleted_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="kb.article_deleted",
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
        select(KbArticle).options(selectinload(KbArticle.tags)).where(KbArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.deleted_at = None
    await db.commit()
    await db.refresh(article)
    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    return _article_to_public(article, breadcrumbs, None, None)
