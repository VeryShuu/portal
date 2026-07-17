"""ARQ cron-tasks for helpdesk (ТЗ §5.1, §8).

* ``poll_helpdesk_mailbox`` — IMAP-фетчер (cron каждые 30 c; реальный интервал
  из ``helpdesk_mailbox_settings.poll_interval_seconds`` применяется внутри
  через Redis ``last_poll_at``); distributed lock ``poll_lock``.
* ``archive_closed_tickets`` — перенос ``closed`` старше
  ``HELPDESK_ARCHIVE_AFTER_DAYS`` в архив.
* ``create_next_helpdesk_archive_partition`` — месячные партиции архива
  (аналог ``create_next_audit_partition``).
* ``cleanup_helpdesk_attachments`` — удаление папок тикетов, архивированных
  > ``HELPDESK_ARCHIVE_FILES_TTL_DAYS`` назад.
* ``send_helpdesk_digest`` — ежедневная email-сводка агентам (cron ежечасно;
  реальное время — из ``helpdesk_digest_settings`` через Redis interval guard).

Все задачи гейтируются модулем (``modules.helpdesk.enabled``): при выключенном
модуле воркеры выходят без работы (ТЗ §9.1, п.5).
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.models.helpdesk import HelpdeskDigestSettings, HelpdeskMailboxSettings
from app.services.helpdesk.archive import archive_closed_tickets, cleanup_archived_files
from app.services.helpdesk.archive_partitions import ensure_helpdesk_archive_partitions
from app.services.helpdesk.digest import (
    DIGEST_LAST_SENT_KEY,
    already_sent_today,
    send_digests,
    should_send_today,
)
from app.services.helpdesk.ingress import (
    LAST_POLL_KEY,
    POLL_LOCK_KEY,
    POLL_LOCK_TTL,
    poll_mailbox,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)

# Distributed lock для digest-воркера (защита от двойного запуска при
# нескольких воркерах; по образцу ``POLL_LOCK_KEY``/``POLL_LOCK_TTL``).
DIGEST_LOCK_KEY = "helpdesk:digest:lock"
DIGEST_LOCK_TTL = 300  # 5 минут — рассылка быстрая, но с запасом.


async def _module_enabled(redis: Redis) -> bool:
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    return bool(modules.helpdesk.enabled)


# ---------------------------------------------------------------------------
# IMAP poll
# ---------------------------------------------------------------------------


async def poll_helpdesk_mailbox(ctx: dict) -> dict:
    """IMAP-фетчер с distributed lock + interval guard."""
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    # Interval guard: реальный интервал — из БД, не из cron-расписания.
    async with AsyncSessionLocal() as db:
        row = (
            (
                await db.execute(
                    select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            return {"skipped": "not_configured"}
        last = await redis.get(LAST_POLL_KEY)
        if last:
            # ARQ-воркер использует Redis-клиент без ``decode_responses=True``
            # (в отличие от ``app.state.redis`` в lifespan) → значение приходит
            # как ``bytes``. Декодируем стойко к обоим типам, иначе
            # ``datetime.fromisoformat`` падает на bytes и поллинг навсегда
            # ломается после первого успешного цикла.
            if isinstance(last, bytes):
                last = last.decode("utf-8", errors="ignore")
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.now(UTC) - last_dt < timedelta(seconds=row.poll_interval_seconds):
                    return {"skipped": "interval_not_elapsed"}
            except ValueError:
                pass  # битое значение — игнорируем, пойдём дальше
        settings_row = row

    # Distributed lock.
    lock_token = secrets.token_hex(16)
    acquired = await redis.set(POLL_LOCK_KEY, lock_token, nx=True, ex=POLL_LOCK_TTL)
    if not acquired:
        return {"skipped": "lock_held"}
    try:
        await redis.set(LAST_POLL_KEY, datetime.now(UTC).isoformat())
        async with AsyncSessionLocal() as db:
            return await poll_mailbox(db, redis, settings_row=settings_row)
    finally:
        with suppress(Exception):
            await redis.eval(_LOCK_RELEASE_LUA, 1, POLL_LOCK_KEY, lock_token)


# ---------------------------------------------------------------------------
# Archive + partition + cleanup
# ---------------------------------------------------------------------------


async def archive_closed_tickets_task(ctx: dict) -> int:
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    async with AsyncSessionLocal() as db:
        return await archive_closed_tickets(db)


async def create_next_helpdesk_archive_partition(ctx: dict) -> str:
    """Создать месячные партиции архива (run_at_startup + ежемесячно)."""
    pg_url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url, statement_cache_size=0)
    try:
        created = await ensure_helpdesk_archive_partitions(conn, months_ahead=3)
        logger.info("helpdesk.archive.partitions_created", tables=created)
        return str(created)
    finally:
        await conn.close()


async def cleanup_helpdesk_attachments_task(ctx: dict) -> int:
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    async with AsyncSessionLocal() as db:
        return await cleanup_archived_files(db)


# ---------------------------------------------------------------------------
# Daily digest email
# ---------------------------------------------------------------------------


async def send_helpdesk_digest(ctx: dict) -> dict:
    """Ежедневная email-сводка по заявкам для helpdesk-агентов.

    Cron запускается ежечасно (``minute=0``); реальное время срабатывания —
    из ``helpdesk_digest_settings`` (``should_send_today``), идемпотентность
    внутри дня — через ``DIGEST_LAST_SENT_KEY``. Distributed lock
    ``DIGEST_LOCK_KEY`` защищает от двойного запуска при нескольких воркерах.
    ``portal_base_url`` — из SystemSettings (runtime, для абсолютных ссылок).
    """
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    now = datetime.now(UTC)

    # Schedule + enabled check.
    async with AsyncSessionLocal() as db:
        row = (
            (await db.execute(select(HelpdeskDigestSettings).where(HelpdeskDigestSettings.id == 1)))
            .scalars()
            .one_or_none()
        )
        if row is None:
            # Миграция не применена/строка удалена — выходим (не крашим воркер).
            return {"skipped": "not_configured"}
        if not should_send_today(
            now,
            enabled=row.enabled,
            digest_hour=row.digest_hour,
            digest_minute=row.digest_minute,
            digest_schedule=row.digest_schedule,
        ):
            return {"skipped": "schedule_mismatch"}

    # Идемпотентность: уже слали сегодня (защита от двойного запуска).
    last = await redis.get(DIGEST_LAST_SENT_KEY)
    if isinstance(last, bytes):
        last = last.decode("utf-8", errors="ignore")
    if already_sent_today(last, now=now):
        return {"skipped": "already_sent_today"}

    # Distributed lock (аналог poll_lock).
    lock_token = secrets.token_hex(16)
    acquired = await redis.set(DIGEST_LOCK_KEY, lock_token, nx=True, ex=DIGEST_LOCK_TTL)
    if not acquired:
        return {"skipped": "lock_held"}
    try:
        portal_base_url = load_system_settings().portal_base_url
        async with AsyncSessionLocal() as db:
            return await send_digests(db, redis, portal_base_url=portal_base_url, now=now)
    finally:
        with suppress(Exception):
            await redis.eval(_LOCK_RELEASE_LUA, 1, DIGEST_LOCK_KEY, lock_token)


__all__ = [
    "archive_closed_tickets_task",
    "cleanup_helpdesk_attachments_task",
    "create_next_helpdesk_archive_partition",
    "poll_helpdesk_mailbox",
    "send_helpdesk_digest",
]
