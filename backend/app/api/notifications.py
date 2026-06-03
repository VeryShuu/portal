"""API уведомлений: список, отметка прочитанным, SSE-стрим."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME
from app.core.system_config import load_system_settings_shared
from app.models.notification import Notification
from app.schemas.notification import NotificationListOut, NotificationOut
from app.services import notifications_sse
from app.services.notifications import get_unread_count
from app.services.notifications_sse import (
    _LUA_CONN_ADD,
    _SSE_BACKOFF_BASE,
    _SSE_BACKOFF_MAX,
    _SSE_CONN_KEY,
    _SSE_GLOBAL_CONN_KEY,
    _SSE_KEEPALIVE_SEC,
    _SSE_SESSION_EXTEND_INTERVAL,
)
from app.services.notifications_sse import (
    sse_generator as _sse_generator,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = get_logger(__name__)

# Re-exported for backwards-compatible imports/patches in tests (the SSE plumbing
# now lives in ``app.services.notifications_sse``).
__all__ = [
    "_LUA_CONN_ADD",
    "_SSE_BACKOFF_BASE",
    "_SSE_BACKOFF_MAX",
    "_SSE_CONN_KEY",
    "_SSE_GLOBAL_CONN_KEY",
    "_SSE_KEEPALIVE_SEC",
    "_SSE_SESSION_EXTEND_INTERVAL",
    "_sse_generator",
    "router",
]


@router.get("", response_model=NotificationListOut, summary="Список уведомлений")
async def list_notifications(
    user: CurrentUser,
    db: DbDep,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NotificationListOut:
    stats_result = await db.execute(
        select(
            func.count().label("total_all"),
            func.count(1).filter(Notification.is_read.is_(False)).label("unread_count"),
        ).where(Notification.user_id == user.id)
    )
    stats = stats_result.one()
    total = stats.unread_count if unread_only else stats.total_all
    unread = stats.unread_count

    items_query = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        items_query = items_query.where(Notification.is_read.is_(False))

    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    )


@router.get("/unread-count", summary="Количество непрочитанных")
async def unread_count(user: CurrentUser, db: DbDep) -> dict[str, int]:
    count = await get_unread_count(db, user.id)
    return {"unread_count": count}


@router.post("/{notification_id}/read", summary="Отметить уведомление прочитанным")
async def mark_read(
    notification_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> dict[str, bool]:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        await db.commit()
    return {"ok": True}


@router.post("/read-all", summary="Отметить все прочитанными")
async def mark_all_read(user: CurrentUser, db: DbDep) -> dict[str, bool]:
    now = datetime.now(UTC)
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return {"ok": True}


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить уведомление",
)
async def delete_notification(
    notification_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> None:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    await db.delete(notif)
    await db.commit()


@router.get("/stream", summary="SSE-стрим уведомлений")
async def notifications_stream(
    request: Request,
    user: CurrentUser,
    redis: RedisDep,
) -> StreamingResponse:
    # Атомарный check-and-add через Lua script — исключает race condition.
    # Проверяет сразу оба лимита: per-user и global.
    # Лимиты читаются из system settings (кэш 60 с), что позволяет менять их без перезапуска.
    sys_cfg = await load_system_settings_shared(redis)
    _max_per_user = sys_cfg.sse_max_connections_per_user
    _max_global = sys_cfg.sse_max_connections_global

    connection_id = uuid.uuid4().hex
    try:
        result = await notifications_sse.try_add_connection(
            redis,
            user_id=user.id,
            connection_id=connection_id,
            max_per_user=_max_per_user,
            max_global=_max_global,
        )
        if result == -1:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many SSE connections (max {_max_per_user} per user)",
            )
        if result == -2:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Server SSE connection limit reached, try again later",
            )
    except HTTPException:
        raise
    except RedisError as exc:
        logger.exception("notifications.sse_limit_redis_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notifications service unavailable",
        ) from exc

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    return StreamingResponse(
        _sse_generator(request, redis, user.id, connection_id, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
