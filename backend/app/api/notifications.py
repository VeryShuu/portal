"""API уведомлений: список, отметка прочитанным, SSE-стрим."""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS
from app.core.system_config import load_system_settings_shared
from app.models.notification import Notification
from app.schemas.notification import NotificationListOut, NotificationOut
from app.services.meetings.realtime import MEETINGS_STREAM_KEY
from app.services.notifications import (
    NOTIFICATIONS_STREAM_KEY,
    get_unread_count,
)
from app.services.photos_realtime import PHOTOS_STREAM_KEY
from app.services.session import _session_key

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = get_logger(__name__)

_SSE_KEEPALIVE_SEC = 20
_SSE_POLL_INTERVAL = 0.5
_SSE_CONNECTION_TTL = 25  # seconds; refreshed each keepalive tick
_SSE_CONN_KEY = "sse:conn:{user_id}"
_SSE_GLOBAL_CONN_KEY = "sse:global"
_SSE_BACKOFF_BASE = 0.5   # seconds; doubles each consecutive error
_SSE_BACKOFF_MAX = 30.0   # cap

_LUA_CONN_ADD = """
local user_key   = KEYS[1]
local global_key = KEYS[2]
local now          = tonumber(ARGV[1])
local score        = tonumber(ARGV[2])
local conn_id      = ARGV[3]
local user_limit   = tonumber(ARGV[4])
local global_limit = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', user_key,   0, now)
redis.call('ZREMRANGEBYSCORE', global_key, 0, now)
local user_cnt = redis.call('ZCARD', user_key)
if user_cnt >= user_limit then return -1 end
local global_cnt = redis.call('ZCARD', global_key)
if global_cnt >= global_limit then return -2 end
redis.call('ZADD', user_key,   score, conn_id)
redis.call('ZADD', global_key, score, conn_id)
redis.call('EXPIRE', user_key,   120)
redis.call('EXPIRE', global_key, 120)
return 1
"""


@router.get("", response_model=NotificationListOut, summary="Список уведомлений")
async def list_notifications(
    user: CurrentUser,
    db: DbDep,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
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


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить уведомление",
)
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


_SSE_SESSION_EXTEND_INTERVAL = 300  # extend session TTL once per 5 minutes


async def _sse_generator(
    request: Request,
    redis,
    user_id: uuid.UUID,
    connection_id: str,
    session_id: str | None,
):
    """Генератор Server-Sent Events через Redis Streams.

    - При подключении сразу отдаёт количество непрочитанных (ping).
    - Читает новые события через XREAD с блокировкой 500 мс.
    - Параллельно читает глобальный поток meetings изменений.
    - Каждые 20 сек отправляет keepalive-комментарий и продлевает TTL коннекта в Redis.
    - Каждые 5 минут продлевает TTL сессии (sliding window для долгоживущего SSE-стрима).
    - Поддерживает Last-Event-ID для replay после реконнекта.
    - Экспоненциальный backoff с jitter при ошибках XREAD (до 30 с).
    - При завершении убирает себя из обоих множеств активных соединений (per-user + global).
    """
    stream_key = NOTIFICATIONS_STREAM_KEY.format(user_id=str(user_id))
    conn_key = _SSE_CONN_KEY.format(user_id=str(user_id))
    # Last-Event-ID may carry a composite "personal|meetings|photos" triple so that all
    # streams can resume from the right offset after a reconnect.
    raw_last = request.headers.get("Last-Event-ID", "$")
    if "|" in raw_last:
        parts = raw_last.split("|")
        last_id = parts[0] or "$"
        last_meetings_id = parts[1] if len(parts) > 1 and parts[1] else "$"
        last_photos_id = parts[2] if len(parts) > 2 and parts[2] else "$"
    else:
        last_id = raw_last
        last_meetings_id = "$"
        last_photos_id = "$"
    keepalive_counter = 0
    consecutive_errors = 0
    _last_session_extend = time.time()

    yield ": connected\n\n"

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                personal_task = asyncio.ensure_future(
                    redis.xread(
                        {stream_key: last_id},
                        count=10,
                        block=int(_SSE_POLL_INTERVAL * 1000),
                    )
                )
                meetings_task = asyncio.ensure_future(
                    redis.xread(
                        {MEETINGS_STREAM_KEY: last_meetings_id},
                        count=10,
                        block=0,
                    )
                )
                photos_task = asyncio.ensure_future(
                    redis.xread(
                        {PHOTOS_STREAM_KEY: last_photos_id},
                        count=20,
                        block=0,
                    )
                )

                personal_results, meetings_results, photos_results = await asyncio.gather(
                    personal_task, meetings_task, photos_task, return_exceptions=True
                )
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                backoff = min(_SSE_BACKOFF_BASE * (2 ** (consecutive_errors - 1)), _SSE_BACKOFF_MAX)
                jitter = random.uniform(0, backoff * 0.2)
                logger.warning(
                    "sse.xread_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    consecutive_errors=consecutive_errors,
                    backoff_sec=round(backoff + jitter, 2),
                )
                await asyncio.sleep(backoff + jitter)
                continue

            if isinstance(personal_results, list) and personal_results:
                for _key, messages in personal_results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        data = json.dumps(fields, ensure_ascii=False)
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield f"id: {composite}\nevent: notification\ndata: {data}\n\n"

            if isinstance(meetings_results, list) and meetings_results:
                for _key, messages in meetings_results:
                    for msg_id, fields in messages:
                        last_meetings_id = msg_id
                        data = json.dumps(fields, ensure_ascii=False)
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield f"id: {composite}\nevent: meeting_changed\ndata: {data}\n\n"

            if isinstance(photos_results, list) and photos_results:
                for _key, messages in photos_results:
                    for msg_id, fields in messages:
                        last_photos_id = msg_id
                        data = json.dumps(fields, ensure_ascii=False)
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield f"id: {composite}\nevent: photo_processed\ndata: {data}\n\n"

            keepalive_counter += 1
            if keepalive_counter * _SSE_POLL_INTERVAL >= _SSE_KEEPALIVE_SEC:
                keepalive_counter = 0
                new_score = time.time() + _SSE_CONNECTION_TTL
                try:
                    async with redis.pipeline(transaction=True) as pipe:
                        pipe.zadd(conn_key, {connection_id: new_score})
                        pipe.zadd(_SSE_GLOBAL_CONN_KEY, {connection_id: new_score})
                        pipe.expire(conn_key, _SSE_CONNECTION_TTL * 2)
                        pipe.expire(_SSE_GLOBAL_CONN_KEY, _SSE_CONNECTION_TTL * 2)
                        await pipe.execute()
                except Exception as _ttl_exc:
                    logger.warning(
                        "sse.ttl_refresh_failed",
                        connection_id=connection_id,
                        error=str(_ttl_exc),
                    )
                now = time.time()
                if session_id and now - _last_session_extend >= _SSE_SESSION_EXTEND_INTERVAL:
                    try:
                        await redis.expire(_session_key(session_id), SESSION_TTL_SECONDS)
                        _last_session_extend = now
                    except Exception as _sess_exc:
                        logger.warning(
                            "sse.session_extend_failed",
                            connection_id=connection_id,
                            error=str(_sess_exc),
                        )
                yield ": keepalive\n\n"
    finally:
        with contextlib.suppress(Exception):
            await redis.zrem(conn_key, connection_id)
        with contextlib.suppress(Exception):
            await redis.zrem(_SSE_GLOBAL_CONN_KEY, connection_id)


@router.get("/stream", summary="SSE-стрим уведомлений")
async def notifications_stream(
    request: Request,
    user: CurrentUser,
    redis: RedisDep,
):
    # Атомарный check-and-add через Lua script — исключает race condition.
    # Проверяет сразу оба лимита: per-user и global.
    # Лимиты читаются из system settings (кэш 60 с), что позволяет менять их без перезапуска.
    sys_cfg = await load_system_settings_shared(redis)
    _max_per_user = sys_cfg.sse_max_connections_per_user
    _max_global = sys_cfg.sse_max_connections_global

    conn_key = _SSE_CONN_KEY.format(user_id=str(user.id))
    now = time.time()
    connection_id = uuid.uuid4().hex
    try:
        result = await redis.eval(  # type: ignore[misc]
            _LUA_CONN_ADD,
            2,
            conn_key,
            _SSE_GLOBAL_CONN_KEY,
            now,  # type: ignore[arg-type]
            now + _SSE_CONNECTION_TTL,  # type: ignore[arg-type]
            connection_id,
            _max_per_user,  # type: ignore[arg-type]
            _max_global,  # type: ignore[arg-type]
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
