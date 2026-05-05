"""Redis session store — хранение токенов по session_id в HTTPOnly cookie."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME

settings = get_settings()
logger = get_logger(__name__)

SESSION_TTL = 8 * 3600  # 8 часов
SESSION_KEY_PREFIX = "session:"
PKCE_KEY_PREFIX = "pkce:"
PKCE_TTL = 600  # 10 минут

_USER_SESSIONS_KEY_PREFIX = "user_sessions:"
_USER_SESSIONS_TTL = SESSION_TTL + 3600


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _pkce_key(state: str) -> str:
    return f"{PKCE_KEY_PREFIX}{state}"


def _user_sessions_key(user_id: str) -> str:
    return f"{_USER_SESSIONS_KEY_PREFIX}{user_id}"


async def save_session(redis: Redis, session_id: str, data: dict[str, Any]) -> None:
    await redis.setex(
        _session_key(session_id),
        SESSION_TTL,
        json.dumps(data),
    )
    user_id = data.get("user_id")
    if user_id:
        key = _user_sessions_key(user_id)
        await redis.sadd(key, session_id)  # type: ignore[misc]
        await redis.expire(key, _USER_SESSIONS_TTL)


async def get_session(redis: Redis, session_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_session_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def delete_session(redis: Redis, session_id: str) -> None:
    raw = await redis.get(_session_key(session_id))
    if raw:
        try:
            data = json.loads(raw)
            user_id = data.get("user_id")
            if user_id:
                await redis.srem(_user_sessions_key(user_id), session_id)  # type: ignore[misc]
        except Exception:
            pass
    await redis.delete(_session_key(session_id))


async def extend_session(redis: Redis, session_id: str) -> None:
    await redis.expire(_session_key(session_id), SESSION_TTL)


async def save_pkce_state(
    redis: Redis,
    state: str,
    verifier: str,
    nonce: str,
    redirect_after: str = "/",
) -> None:
    data = {
        "verifier": verifier,
        "nonce": nonce,
        "redirect_after": redirect_after,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await redis.setex(_pkce_key(state), PKCE_TTL, json.dumps(data))


async def get_pkce_state(redis: Redis, state: str) -> dict[str, Any] | None:
    raw = await redis.get(_pkce_key(state))
    if raw is None:
        return None
    return json.loads(raw)


async def get_and_delete_pkce_state(redis: Redis, state: str) -> dict[str, Any] | None:
    raw = await redis.getdel(_pkce_key(state))
    if raw is None:
        return None
    return json.loads(raw)


async def delete_pkce_state(redis: Redis, state: str) -> None:
    await redis.delete(_pkce_key(state))


async def invalidate_all_user_sessions(
    redis: Redis, user_id: str, except_session_id: str | None = None
) -> int:
    key = _user_sessions_key(user_id)
    session_ids = await redis.smembers(key)  # type: ignore[misc]
    count = 0
    for sid in session_ids:
        if except_session_id and sid == except_session_id:
            continue
        await redis.delete(_session_key(sid))
        count += 1
    await redis.delete(key)
    return count


async def get_session_from_request(request: Request, redis: Redis) -> dict[str, Any] | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return await get_session(redis, session_id)
