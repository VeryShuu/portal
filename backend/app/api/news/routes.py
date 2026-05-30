"""Main news CRUD routes (list / get / create / update / delete / restore / purge / versions)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.api.deps import AdminDep, CurrentUser, DbDep, EditorDep, RedisDep
from app.api.news_categories import ensure_category_exists
from app.core.constants import IDEMPOTENCY_TTL, VIEW_DEDUP_TTL_SECONDS
from app.core.system_config import load_system_settings
from app.models.news import News as NewsModel
from app.schemas.news import (
    CreateNewsRequest,
    NewsList,
    NewsPublic,
    NewsUploadLimits,
    NewsVersionPublic,
    NewsWithAuthor,
    TrashNewsList,
    UpdateNewsRequest,
)
from app.services import news as news_svc

from ._common import emit_news_audit, require_news_read_access

router = APIRouter()


async def _get_news_or_404(
    db: DbDep, news_id: uuid.UUID, *, include_deleted: bool = False
) -> NewsModel:
    news = await news_svc.get_news_by_id(db, news_id, include_deleted=include_deleted)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return news


@router.get("", response_model=NewsList, summary="Список новостей")
async def list_news(
    user: CurrentUser,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    limit: int | None = Query(default=None, ge=1, le=100, description="Alias for page_size"),
    offset: int | None = Query(default=None, ge=0, description="Offset alias (overrides page)"),
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    is_pinned: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200, description="FTS по заголовку и тексту"),
) -> NewsList:
    if limit is not None:
        page_size = limit

    if status_filter and status_filter not in ("draft", "published", "archived"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )
    if status_filter in ("draft", "archived") and user.role not in ("editor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    items, total = await news_svc.get_news_list(
        db,
        user=user,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
        category=category,
        is_pinned=is_pinned,
        q=q or None,
        offset_override=offset,
    )
    return NewsList(
        items=[NewsPublic.model_validate(n) for n in items],
        total=total,
    )


@router.get("/limits", response_model=NewsUploadLimits, summary="Лимиты загрузки файлов новостей")
async def get_news_upload_limits(_: CurrentUser) -> NewsUploadLimits:
    s = load_system_settings()
    return NewsUploadLimits(news_attachment_max_size_mb=s.news_attachment_max_size_mb)


@router.get("/trash", response_model=TrashNewsList, summary="Корзина: список удалённых новостей")
async def list_trash_news(
    admin: AdminDep,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TrashNewsList:
    items, total = await news_svc.get_trash_news(db, page=page, page_size=page_size)
    return TrashNewsList(
        items=[NewsWithAuthor.model_validate(n) for n in items],
        total=total,
    )


@router.get("/{news_id}", response_model=NewsPublic, summary="Получить новость")
async def get_news(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id)
    require_news_read_access(news, user)

    dedup_key = f"view:news:{news_id}:{user.id}"
    if not await redis.exists(dedup_key):
        await redis.setex(dedup_key, VIEW_DEDUP_TTL_SECONDS, "1")
        await news_svc.increment_view_count(db, news_id)
        await db.refresh(news, attribute_names=["view_count"])

    return NewsPublic.model_validate(news)


@router.post(
    "", response_model=NewsPublic, status_code=status.HTTP_201_CREATED, summary="Создать новость"
)
async def create_news(
    body: CreateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> NewsPublic:
    if idempotency_key:
        cached = await redis.get(f"idem:news:{editor.id}:{idempotency_key}")
        if cached:
            return NewsPublic.model_validate_json(cached)

    news = await news_svc.create_news(db, author=editor, data=body.model_dump())
    for cat in body.categories:
        ensure_category_exists(cat)
    await emit_news_audit(
        redis,
        event_type="news.created",
        actor=editor,
        request=request,
        resource_id=str(news.id),
        resource_title=news.title,
    )
    public = NewsPublic.model_validate(news)
    if idempotency_key:
        await redis.set(
            f"idem:news:{editor.id}:{idempotency_key}",
            public.model_dump_json(),
            ex=IDEMPOTENCY_TTL,
        )
    return public


@router.put("/{news_id}", response_model=NewsPublic, summary="Обновить новость")
async def update_news(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id)
    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    for cat in body.categories or []:
        ensure_category_exists(cat)
    await emit_news_audit(
        redis,
        event_type="news.updated",
        actor=editor,
        request=request,
        resource_id=str(news_id),
        resource_title=updated.title,
    )
    return NewsPublic.model_validate(updated)


@router.put("/{news_id}/draft", response_model=NewsPublic, summary="Автосохранение черновика")
async def save_draft(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id)
    if news.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only drafts can be auto-saved this way"
        )
    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    return NewsPublic.model_validate(updated)


@router.delete(
    "/{news_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить новость (soft)"
)
async def delete_news(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    news = await _get_news_or_404(db, news_id)
    await news_svc.delete_news(db, news)
    await emit_news_audit(
        redis,
        event_type="news.deleted",
        actor=editor,
        request=request,
        resource_id=str(news_id),
        resource_title=news.title,
    )


@router.post(
    "/{news_id}/restore", response_model=NewsPublic, summary="Восстановить удалённую новость"
)
async def restore_news(
    news_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await _get_news_or_404(db, news_id, include_deleted=True)
    if news.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="News is not deleted")
    news = await news_svc.restore_news(db, news)
    await emit_news_audit(
        redis,
        event_type="news.restored",
        actor=admin,
        request=request,
        resource_id=str(news_id),
        resource_title=news.title,
    )
    return NewsPublic.model_validate(news)


@router.delete(
    "/{news_id}/purge", status_code=status.HTTP_204_NO_CONTENT, summary="Hard-delete новости"
)
async def purge_news(
    news_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    news = await _get_news_or_404(db, news_id, include_deleted=True)
    if news.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="News is not deleted")
    title = news.title
    await news_svc.purge_news(db, news)
    await emit_news_audit(
        redis,
        event_type="news.purged",
        actor=admin,
        request=request,
        resource_id=str(news_id),
        resource_title=title,
    )


@router.get("/{news_id}/versions", response_model=list[NewsVersionPublic], summary="История версий")
async def get_versions(
    news_id: uuid.UUID,
    _: EditorDep,
    db: DbDep,
) -> list[NewsVersionPublic]:
    await _get_news_or_404(db, news_id)
    versions = await news_svc.get_news_versions(db, news_id)
    return [NewsVersionPublic.model_validate(v) for v in versions]
