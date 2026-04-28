"""API уведомлений: список, отметка прочитанным, SSE-стрим."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.models.notification import Notification
from app.schemas.notification import NotificationListOut, NotificationOut
from app.services.notifications import (
    NOTIFICATIONS_STREAM_KEY,
    get_unread_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = get_logger(__name__)

_SSE_KEEPALIVE_SEC = 20
_SSE_POLL_INTERVAL = 0.5
_SSE_MAX_CONNECTIONS_PER_USER = 10
_SSE_CONNECTION_TTL = 25  # seconds; refreshed each keepalive tick
_SSE_CONN_KEY = "sse:conn:{user_id}"


@router.get("", response_model=NotificationListOut, summary="Список уведомлений")
async def list_notifications(
    user: CurrentUser,
    db: DbDep,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Notification).where(Notification.user_id == user.id)
    count_query = select(func.count()).where(Notification.user_id == user.id)

    if unread_only:
        query = query.where(Notification.is_read.is_(False))
        count_query = count_query.where(Notification.is_read.is_(False))

    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    items_result = await db.execute(query)
    items = items_result.scalars().all()

    unread = await get_unread_count(db, user.id)

    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    )


@router.get("/unread-count", summary="Количество непрочитанных")
async def unread_count(user: CurrentUser, db: DbDep):
    count = await get_unread_count(db, user.id)
    return {"unread_count": count}


@router.post("/{notification_id}/read", summary="Отметить уведомление прочитанным")
async def mark_read(
    notification_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
):
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
async def mark_all_read(user: CurrentUser, db: DbDep):
    now = datetime.now(UTC)
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить уведомление")
async def delete_notification(
    notification_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
):
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


async def _sse_generator(request: Request, redis, user_id: uuid.UUID, connection_id: str):
    """Генератор Server-Sent Events через Redis Streams.

    - При подключении сразу отдаёт количество непрочитанных (ping).
    - Читает новые события через XREAD с блокировкой 500 мс.
    - Каждые 20 сек отправляет keepalive-комментарий и продлевает TTL коннекта в Redis.
    - Поддерживает Last-Event-ID для replay после реконнекта.
    - При завершении убирает себя из множества активных соединений пользователя.
    """
    stream_key = NOTIFICATIONS_STREAM_KEY.format(user_id=str(user_id))
    conn_key = _SSE_CONN_KEY.format(user_id=str(user_id))
    last_id = request.headers.get("Last-Event-ID", "$")
    keepalive_counter = 0

    yield ": connected\n\n"

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                results = await redis.xread(
                    {stream_key: last_id},
                    count=10,
                    block=int(_SSE_POLL_INTERVAL * 1000),
                )
            except Exception as exc:
                logger.exception("sse.xread_failed", error=str(exc), error_type=type(exc).__name__)
                await asyncio.sleep(1)
                continue

            if results:
                for _key, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        data = json.dumps(fields, ensure_ascii=False)
                        yield f"id: {msg_id}\nevent: notification\ndata: {data}\n\n"

            keepalive_counter += 1
            if keepalive_counter * _SSE_POLL_INTERVAL >= _SSE_KEEPALIVE_SEC:
                keepalive_counter = 0
                # продлеваем TTL записи о соединении
                try:
                    await redis.zadd(conn_key, {connection_id: asyncio.get_event_loop().time() + _SSE_CONNECTION_TTL})
                    await redis.expire(conn_key, _SSE_CONNECTION_TTL * 2)
                except Exception:
                    pass
                yield ": keepalive\n\n"
    finally:
        try:
            await redis.zrem(conn_key, connection_id)
        except Exception:
            pass


@router.get("/stream", summary="SSE-стрим уведомлений")
async def notifications_stream(
    request: Request,
    user: CurrentUser,
    redis: RedisDep,
):
    # Лимит одновременных SSE-коннектов на пользователя (DoS-защита).
    # Используем sorted set: score = expiry, ZADD + ZREMRANGEBYSCORE(stale) + ZCARD.
    conn_key = _SSE_CONN_KEY.format(user_id=str(user.id))
    now = asyncio.get_event_loop().time()
    connection_id = uuid.uuid4().hex
    try:
        await redis.zremrangebyscore(conn_key, 0, now)
        active = await redis.zcard(conn_key)
        if active >= _SSE_MAX_CONNECTIONS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many SSE connections (max {_SSE_MAX_CONNECTIONS_PER_USER} per user)",
            )
        await redis.zadd(conn_key, {connection_id: now + _SSE_CONNECTION_TTL})
        await redis.expire(conn_key, _SSE_CONNECTION_TTL * 2)
    except HTTPException:
        raise
    except RedisError as exc:
        logger.exception("notifications.sse_limit_redis_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notifications service unavailable",
        )

    return StreamingResponse(
        _sse_generator(request, redis, user.id, connection_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
