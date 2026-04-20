"""News API: CRUD новостей."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.logging import get_logger
from app.schemas.news import (
    CreateNewsRequest,
    NewsList,
    NewsPublic,
    NewsVersionPublic,
    UpdateNewsRequest,
)
from app.services import news as news_svc
from app.services.audit import push_audit_event

router = APIRouter(prefix="/news", tags=["news"])
logger = get_logger(__name__)

VIEW_DEDUP_TTL = 3600  # 1 час


@router.get("", response_model=NewsList, summary="Список новостей")
async def list_news(
    user: CurrentUser,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> NewsList:
    if status_filter and status_filter not in ("draft", "published", "archived"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")

    if status_filter in ("draft", "archived") and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    items, total = await news_svc.get_news_list(
        db, user=user, status_filter=status_filter, page=page, page_size=page_size
    )
    return NewsList(items=items, total=total)


@router.get("/{news_id}", response_model=NewsPublic, summary="Получить новость")
async def get_news(
    news_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    if news.status != "published" and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    dedup_key = f"view:news:{news_id}:{user.id}"
    if not await redis.exists(dedup_key):
        await redis.setex(dedup_key, VIEW_DEDUP_TTL, "1")
        await news_svc.increment_view_count(db, news_id)

    return news


@router.post("", response_model=NewsPublic, status_code=status.HTTP_201_CREATED, summary="Создать новость")
async def create_news(
    body: CreateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.create_news(db, author=editor, data=body.model_dump())
    await push_audit_event(
        redis,
        event_type="news.created",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news.id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )
    return news


@router.put("/{news_id}", response_model=NewsPublic, summary="Обновить новость")
async def update_news(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    await push_audit_event(
        redis,
        event_type="news.updated",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=updated.title,
        ip_address=request.client.host if request.client else None,
    )
    return updated


@router.put("/{news_id}/draft", response_model=NewsPublic, summary="Автосохранение черновика")
async def save_draft(
    news_id: uuid.UUID,
    body: UpdateNewsRequest,
    editor: EditorDep,
    db: DbDep,
) -> NewsPublic:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    if news.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only drafts can be auto-saved this way")

    updated = await news_svc.update_news(
        db, news=news, editor=editor, data=body.model_dump(exclude_none=True)
    )
    return updated


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить новость (soft)")
async def delete_news(
    news_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> None:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    await news_svc.delete_news(db, news)
    await push_audit_event(
        redis,
        event_type="news.deleted",
        user_id=str(editor.id),
        user_email=editor.email,
        resource_type="news",
        resource_id=str(news_id),
        resource_title=news.title,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/{news_id}/versions", response_model=list[NewsVersionPublic], summary="История версий")
async def get_versions(
    news_id: uuid.UUID,
    _: EditorDep,
    db: DbDep,
) -> list[NewsVersionPublic]:
    news = await news_svc.get_news_by_id(db, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return await news_svc.get_news_versions(db, news_id)
