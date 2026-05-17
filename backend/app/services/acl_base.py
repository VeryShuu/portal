"""Общая инфраструктура ACL-кэша, используемая kb_acl.py, photos_acl.py и files_acl.py."""

from __future__ import annotations

import contextlib
from typing import cast

from redis.asyncio import Redis

from app.models.user import User

ACL_TTL = 300  # 5 минут — TTL записей в Redis

SYSTEM_ALL_USERS_SUBJECT_ID = "__all_users__"
SYSTEM_ALL_USERS_NAME = "Все пользователи"


async def get_cached(redis: Redis, key: str) -> str | None:
    try:
        return cast(str | None, await redis.get(key))
    except Exception:
        return None


async def set_cached(redis: Redis, key: str, value: str) -> None:
    with contextlib.suppress(Exception):
        await redis.setex(key, ACL_TTL, value)


async def scan_and_delete(redis: Redis, pattern: str, batch: int = 500) -> None:
    """Non-blocking очистка Redis-ключей через SCAN + пакетный DELETE.

    Не использует KEYS() — тот блокирует весь Redis при большом keyspace.
    """
    keys_buf: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=batch):
        keys_buf.append(key)
        if len(keys_buf) >= batch:
            await redis.delete(*keys_buf)
            keys_buf.clear()
    if keys_buf:
        await redis.delete(*keys_buf)


async def subject_ids_for_user(user: User) -> list[str]:
    """Возвращает список subject_id: str(user.id) + keycloak_id + группы Keycloak.

    Локальные пользователи (auth_source='local') не имеют keycloak_id — всегда
    включаем str(user.id), который используется при ручной выдаче прав.
    """
    ids: list[str] = [str(user.id), SYSTEM_ALL_USERS_SUBJECT_ID]
    if user.keycloak_id:
        ids.append(user.keycloak_id)
    if hasattr(user, "keycloak_groups") and user.keycloak_groups:
        groups = user.keycloak_groups
        if isinstance(groups, list):
            for g in groups:
                gs = str(g)
                if not gs:
                    continue
                ids.append(gs)
                if gs.startswith("/"):
                    stripped = gs.lstrip("/")
                    if stripped:
                        ids.append(stripped)
                else:
                    ids.append("/" + gs)
    seen: set[str] = set()
    deduped: list[str] = []
    for sid in ids:
        if sid not in seen:
            seen.add(sid)
            deduped.append(sid)
    return deduped
