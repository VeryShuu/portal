"""Redis session store — хранение токенов по session_id в HTTPOnly cookie."""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any, cast

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

# Per-session refresh lock — сериализует параллельные /auth/refresh из одного
# браузера (несколько вкладок / гонка silent-refresh с retry-on-401), чтобы
# ротация refresh-токена в Keycloak не инвалидировала «соседние» потоки.
#
# Инварианты таймингов (критично!):
#   TTL  > _KC_CLIENT_TIMEOUT (10s)  — лок переживает самый медленный refresh,
#                                      иначе он истечёт «под лидером» и «ждун»
#                                      пойдёт без лока со старым refresh-токеном.
#   WAIT >= TTL                      — ждём не меньше, чем лок может легитимно
#                                      удерживаться лидером, иначе сдадимся рано
#                                      и устроим ровно ту гонку, что чиним.
_REFRESH_LOCK_PREFIX = "refresh_lock:"
_REFRESH_LOCK_TTL_MS = 15_000
_REFRESH_LOCK_WAIT_MS = 15_000
_REFRESH_LOCK_POLL_MS = 50

# Окно коалесинга: если сессию обновили буквально только что, соседний поток не
# дёргает Keycloak повторно (access-токен заведомо ещё жив, KC lifespan ≥ 5 мин)
# — гасит мультитаб-бурст и лишнюю ротацию refresh-токена.
REFRESH_COALESCE_WINDOW_S = 10.0

_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


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
    return cast(dict[str, Any], json.loads(raw))


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
    return cast(dict[str, Any], json.loads(raw))


async def get_and_delete_pkce_state(redis: Redis, state: str) -> dict[str, Any] | None:
    raw = await redis.getdel(_pkce_key(state))
    if raw is None:
        return None
    return cast(dict[str, Any], json.loads(raw))


async def delete_pkce_state(redis: Redis, state: str) -> None:
    await redis.delete(_pkce_key(state))


async def invalidate_all_user_sessions(
    redis: Redis, user_id: str, except_session_id: str | None = None
) -> int:
    key = _user_sessions_key(user_id)
    session_ids = await redis.smembers(key)  # type: ignore[misc]
    count = 0
    invalidated_sids: list[str] = []
    for sid in session_ids:
        if except_session_id and sid == except_session_id:
            continue
        await redis.delete(_session_key(sid))
        invalidated_sids.append(sid)
        count += 1
    if except_session_id:
        if invalidated_sids:
            await redis.srem(key, *invalidated_sids)  # type: ignore[misc]
    else:
        await redis.delete(key)
    return count


async def get_session_from_request(request: Request, redis: Redis) -> dict[str, Any] | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return await get_session(redis, session_id)


def _refresh_lock_key(session_id: str) -> str:
    return f"{_REFRESH_LOCK_PREFIX}{session_id}"


async def acquire_refresh_lock(redis: Redis, session_id: str) -> str | None:
    """Best-effort per-session lock. Returns a token on success, ``None`` on timeout."""
    key = _refresh_lock_key(session_id)
    token = secrets.token_hex(16)
    attempts = max(1, _REFRESH_LOCK_WAIT_MS // _REFRESH_LOCK_POLL_MS)
    for _ in range(attempts):
        if await redis.set(key, token, nx=True, px=_REFRESH_LOCK_TTL_MS):
            return token
        await asyncio.sleep(_REFRESH_LOCK_POLL_MS / 1000)
    return None


async def release_refresh_lock(redis: Redis, session_id: str, token: str) -> None:
    """Release the lock only if we still own it (compare-and-delete)."""
    with contextlib.suppress(Exception):
        await redis.eval(_RELEASE_LOCK_LUA, 1, _refresh_lock_key(session_id), token)  # type: ignore[misc]
