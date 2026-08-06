"""ARQ-задача ежедневного пересчёта ``users.current_status``.

ERP-импорт отсутствий уже пересчитывает статус для затронутых пользователей
(см. :func:`absences_importer.run_absences_import`). Эта задача — **полный
пересчёт** для перехода дат: отпуск кончился вчера → сегодня пользователь уже
``working``; больничный начался сегодня → ``sick``. Запускается раз в сутки
cron'ом в 00:05.

Гейтинг: только мастер-переключатель ``modules.erp_sync.enabled`` (поллинг
отсутствий не обязателен — статус может поддерживаться ручной загрузкой файла).
Distributed-lock защищает от наложений.
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from typing import TYPE_CHECKING

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.erp_sync.absences_status import recompute_current_status

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

RECOMPUTE_LOCK_KEY = "erp_absences:status:recompute_lock"
RECOMPUTE_LOCK_TTL = 300  # 5 минут — пересчёт ~300 пользователей быстрый.

_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    return token if acquired else None


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    with suppress(Exception):
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]


async def _module_enabled(redis: Redis) -> bool:
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    return bool(modules.erp_sync.enabled)


async def recompute_daily_presence_status(ctx: dict) -> dict:
    """Ежедневный полный пересчёт ``current_status`` для всех пользователей.

    Возвращает ``{"skipped": ...}`` (модуль выключен / lock занят) или
    ``{"updated": N}`` (количество обновлённых строк).
    """
    redis: Redis | None = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    lock_token = await _acquire_lock(redis, RECOMPUTE_LOCK_KEY, RECOMPUTE_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    try:
        # Полный пересчёт: для каждого пользователя с активной absence —
        # приоритетная категория; без активной — сброс в working отдельным шагом.
        async with AsyncSessionLocal() as db:
            await recompute_current_status(db, None)
            # Сброс users, у которых absence закончилась, но статус ещё устаревший.
            # recompute_current_status(None) покрывает только JOIN с active;
            # добиваем reset для всех, кто не попал в active, но имеет не-working статус.
            from sqlalchemy import text

            await db.execute(
                text(
                    """
                    UPDATE users
                    SET current_status = 'working', current_status_until = NULL
                    WHERE current_status <> 'working'
                      AND NOT EXISTS (
                          SELECT 1 FROM erp_absences ea
                          WHERE ea.user_id = users.id
                            AND ea.start_date <= CURRENT_DATE
                            AND ea.end_date >= CURRENT_DATE
                      )
                    """
                )
            )
            await db.commit()
        logger.info("erp_sync.presence_status.daily_recomputed")
        return {"updated": "ok"}
    finally:
        await _release_lock(redis, RECOMPUTE_LOCK_KEY, lock_token)
