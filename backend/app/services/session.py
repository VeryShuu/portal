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


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _pkce_key(state: str) -> str:
    return f"{PKCE_KEY_PREFIX}{state}"


async def save_session(redis: Redis, session_id: str, data: dict[str, Any]) -> None:
    await redis.setex(
        _session_key(session_id),
        SESSION_TTL,
        json.dumps(data),
    )


async def get_session(redis: Redis, session_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_session_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def delete_session(redis: Redis, session_id: str) -> None:
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


async def delete_pkce_state(redis: Redis, state: str) -> None:
    await redis.delete(_pkce_key(state))


async def get_session_from_request(request: Request, redis: Redis) -> dict[str, Any] | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return await get_session(redis, session_id)
