"""SSE orchestration for the notifications stream.

Houses the Server-Sent-Events plumbing that previously lived inside the API
handler: the Last-Event-ID parser, the SSE-frame formatter, the Redis-Streams
reader over the personal / meetings / photos streams, and the connection-limit
lifecycle (atomic Lua add, TTL refresh, cleanup). The API layer keeps only the
thin HTTP boundary (ACL, limit→HTTP translation, ``StreamingResponse``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.security import SESSION_TTL_SECONDS
from app.services.meetings.realtime import MEETINGS_STREAM_KEY
from app.services.notifications import NOTIFICATIONS_STREAM_KEY
from app.services.photos_realtime import PHOTOS_STREAM_KEY
from app.services.session import _session_key

logger = get_logger(__name__)

_SSE_KEEPALIVE_SEC = 20
_SSE_POLL_INTERVAL = 0.5
_SSE_CONNECTION_TTL = 25  # seconds; refreshed each keepalive tick
_SSE_CONN_KEY = "sse:conn:{user_id}"
_SSE_GLOBAL_CONN_KEY = "sse:global"
_SSE_BACKOFF_BASE = 0.5  # seconds; doubles each consecutive error
_SSE_BACKOFF_MAX = 30.0  # cap
_SSE_SESSION_EXTEND_INTERVAL = 300  # extend session TTL once per 5 minutes

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


# ── Last-Event-ID parser / SSE-frame formatter ────────────────────────────────


def parse_last_event_id(raw: str) -> tuple[str, str, str]:
    """Split a Last-Event-ID into per-stream offsets.

    The id may be a composite ``"personal|meetings|photos"`` triple so all three
    streams can resume from the right offset after a reconnect. Missing or empty
    parts fall back to ``"$"`` (only new entries).
    """
    if "|" in raw:
        parts = raw.split("|")
        last_id = parts[0] or "$"
        last_meetings_id = parts[1] if len(parts) > 1 and parts[1] else "$"
        last_photos_id = parts[2] if len(parts) > 2 and parts[2] else "$"
        return last_id, last_meetings_id, last_photos_id
    return raw, "$", "$"


def format_sse_event(event: str, composite_id: str, fields: Any) -> str:
    """Render one SSE frame with a composite id and JSON-serialized payload."""
    data = json.dumps(fields, ensure_ascii=False)
    return f"id: {composite_id}\nevent: {event}\ndata: {data}\n\n"


# ── Connection-limit lifecycle ────────────────────────────────────────────────


async def try_add_connection(
    redis: Redis,
    *,
    user_id: uuid.UUID,
    connection_id: str,
    max_per_user: int,
    max_global: int,
) -> int:
    """Atomically register an SSE connection respecting per-user/global limits.

    Returns the Lua script result: ``1`` on success, ``-1`` when the per-user
    limit is reached, ``-2`` when the global limit is reached. May raise
    ``RedisError`` which the caller translates to a 503.
    """
    conn_key = _SSE_CONN_KEY.format(user_id=str(user_id))
    now = time.time()
    result = await redis.eval(
        _LUA_CONN_ADD,
        2,
        conn_key,
        _SSE_GLOBAL_CONN_KEY,
        now,
        now + _SSE_CONNECTION_TTL,
        connection_id,
        max_per_user,
        max_global,
    )
    return int(result)


async def _refresh_connection_ttl(redis: Redis, conn_key: str, connection_id: str) -> None:
    new_score = time.time() + _SSE_CONNECTION_TTL
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zadd(conn_key, {connection_id: new_score})
            pipe.zadd(_SSE_GLOBAL_CONN_KEY, {connection_id: new_score})
            pipe.expire(conn_key, _SSE_CONNECTION_TTL * 2)
            pipe.expire(_SSE_GLOBAL_CONN_KEY, _SSE_CONNECTION_TTL * 2)
            await pipe.execute()
    except Exception as exc:
        logger.warning(
            "sse.ttl_refresh_failed",
            connection_id=connection_id,
            error=str(exc),
        )


async def _maybe_extend_session(
    redis: Redis, session_id: str | None, connection_id: str, last_extend: float
) -> float:
    now = time.time()
    if session_id and now - last_extend >= _SSE_SESSION_EXTEND_INTERVAL:
        try:
            await redis.expire(_session_key(session_id), SESSION_TTL_SECONDS)
            return now
        except Exception as exc:
            logger.warning(
                "sse.session_extend_failed",
                connection_id=connection_id,
                error=str(exc),
            )
    return last_extend


async def _cleanup_connection(redis: Redis, conn_key: str, connection_id: str) -> None:
    with contextlib.suppress(Exception):
        await redis.zrem(conn_key, connection_id)
    with contextlib.suppress(Exception):
        await redis.zrem(_SSE_GLOBAL_CONN_KEY, connection_id)


# ── SSE orchestration ─────────────────────────────────────────────────────────


async def sse_generator(
    request: Request,
    redis: Redis,
    user_id: uuid.UUID,
    connection_id: str,
    session_id: str | None,
) -> AsyncIterator[str]:
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
    last_id, last_meetings_id, last_photos_id = parse_last_event_id(
        request.headers.get("Last-Event-ID", "$")
    )
    keepalive_counter = 0
    consecutive_errors = 0
    last_session_extend = time.time()

    yield ": connected\n\n"

    try:
        while True:
            if await request.is_disconnected():
                break

            personal_results: Any = None
            meetings_results: Any = None
            photos_results: Any = None
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
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield format_sse_event("notification", composite, fields)

            if isinstance(meetings_results, list) and meetings_results:
                for _key, messages in meetings_results:
                    for msg_id, fields in messages:
                        last_meetings_id = msg_id
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield format_sse_event("meeting_changed", composite, fields)

            if isinstance(photos_results, list) and photos_results:
                for _key, messages in photos_results:
                    for msg_id, fields in messages:
                        last_photos_id = msg_id
                        composite = f"{last_id}|{last_meetings_id}|{last_photos_id}"
                        yield format_sse_event("photo_processed", composite, fields)

            keepalive_counter += 1
            if keepalive_counter * _SSE_POLL_INTERVAL >= _SSE_KEEPALIVE_SEC:
                keepalive_counter = 0
                await _refresh_connection_ttl(redis, conn_key, connection_id)
                last_session_extend = await _maybe_extend_session(
                    redis, session_id, connection_id, last_session_extend
                )
                yield ": keepalive\n\n"
    finally:
        await _cleanup_connection(redis, conn_key, connection_id)
