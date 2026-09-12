"""Redis-сессии внешних обучаемых (learner).

Отдельное пространство ключей ``learning_session:*`` — принципалы типизированы,
портальные ``session:*`` не пересекаются и не читаются взаимно (ТЗ §7):
``get_current_user`` портала эти сессии не видит, learner-deps не читают
портальные. TTL 8ч со скользящим окном (sliding window на каждом успешном
resolve). Индекс ``learning_sessions:{account_id}`` — для «выйти со всех
устройств» (инвалидация по блокировке учётки).
"""

from __future__ import annotations

import json
from typing import Any, cast

from redis.asyncio import Redis

SESSION_TTL = 8 * 3600  # 8 часов, как портальные сессии
SESSION_KEY_PREFIX = "learning_session:"
_SESSIONS_INDEX_PREFIX = "learning_sessions:"  # set: все живые session_id учётки
_INDEX_TTL = SESSION_TTL + 3600

COOKIE_NAME = "learning_session"


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _index_key(account_id: str) -> str:
    return f"{_SESSIONS_INDEX_PREFIX}{account_id}"


async def save_session(
    redis: Redis, session_id: str, account_id: str, data: dict[str, Any]
) -> None:
    await redis.setex(_session_key(session_id), SESSION_TTL, json.dumps(data))
    key = _index_key(account_id)
    await redis.sadd(key, session_id)  # type: ignore[misc]  # redis-py async-overload typing
    await redis.expire(key, _INDEX_TTL)


async def get_session_payload(redis: Redis, session_id: str) -> dict[str, Any] | None:
    """Возвращает payload и продлевает TTL (sliding window).

    Индекс учётки продлевается ВМЕСТЕ с сессией и восстанавливается, если
    истёк (TTL индекса считается от логина): иначе при активной сессии
    старше 9ч индекс исчезает, и invalidate_all_sessions («выйти со всех
    устройств» при сбросе пароля/блокировке) сессию больше не находит."""
    raw = await redis.get(_session_key(session_id))
    if raw is None:
        return None
    await redis.expire(_session_key(session_id), SESSION_TTL)
    data = cast(dict[str, Any], json.loads(raw))
    account_id = data.get("account_id")
    if account_id:
        key = _index_key(str(account_id))
        await redis.sadd(key, session_id)  # type: ignore[misc]  # redis-py async-overload typing
        await redis.expire(key, _INDEX_TTL)
    return data


async def delete_session(redis: Redis, session_id: str) -> None:
    raw = await redis.get(_session_key(session_id))
    if raw:
        try:
            data = cast(dict[str, Any], json.loads(raw))
            account_id = data.get("account_id")
            if account_id:
                await redis.srem(_index_key(str(account_id)), session_id)  # type: ignore[misc]
        except Exception:  # битый payload не мешает удалить сам ключ
            pass
    await redis.delete(_session_key(session_id))


async def invalidate_all_sessions(redis: Redis, account_id: str) -> int:
    """«Выйти со всех устройств»: постоянная блокировка учётки."""
    key = _index_key(account_id)
    session_ids = await redis.smembers(key)  # type: ignore[misc]
    count = 0
    for sid in session_ids:
        await redis.delete(_session_key(sid))
        count += 1
    await redis.delete(key)
    return count


def build_login_payload(account_id: str) -> dict[str, Any]:
    # Ограниченные сессии (restricted_to) упразднены вместе с паролями;
    # сессии, созданные до этого, содержали лишнее поле — резолвер его игнорирует.
    return {
        "principal_type": "learning_account",
        "account_id": account_id,
    }
