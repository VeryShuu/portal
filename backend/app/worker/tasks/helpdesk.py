"""ARQ cron-tasks for helpdesk (ТЗ §5.1, §8).

* ``poll_helpdesk_mailbox`` — IMAP-фетчер (cron каждые 30 c; реальный интервал
  из ``helpdesk_mailbox_settings.poll_interval_seconds`` применяется внутри
  через Redis ``last_poll_at``); distributed lock ``poll_lock``.
* ``auto_close_resolved_tickets`` — ``resolved → closed`` для тикетов без
  активности ≥ ``HELPDESK_RESOLVED_AUTO_CLOSE_DAYS``.
* ``archive_closed_tickets`` — перенос ``closed`` старше
  ``HELPDESK_ARCHIVE_AFTER_DAYS`` в архив.
* ``create_next_helpdesk_archive_partition`` — месячные партиции архива
  (аналог ``create_next_audit_partition``).
* ``cleanup_helpdesk_attachments`` — удаление папок тикетов, архивированных
  > ``HELPDESK_ARCHIVE_FILES_TTL_DAYS`` назад.

Все задачи гейтируются модулем (``modules.helpdesk.enabled``): при выключенном
модуле воркеры выходят без работы (ТЗ §9.1, п.5).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.constants import (
    HELPDESK_RESOLVED_AUTO_CLOSE_DAYS,
)
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskMailboxSettings, HelpdeskTicket
from app.services.helpdesk.archive import archive_closed_tickets, cleanup_archived_files
from app.services.helpdesk.archive_partitions import ensure_helpdesk_archive_partitions
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
            await db.execute(
                select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
            )
        ).scalars().one_or_none()
        if row is None:
            return {"skipped": "not_configured"}
        last = await redis.get(LAST_POLL_KEY)
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.now(UTC) - last_dt < timedelta(
                    seconds=row.poll_interval_seconds
                ):
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
        with _Suppress():
            await redis.eval(_LOCK_RELEASE_LUA, 1, POLL_LOCK_KEY, lock_token)


# ---------------------------------------------------------------------------
# Auto-close resolved
# ---------------------------------------------------------------------------


async def auto_close_resolved_tickets(ctx: dict) -> int:
    """``resolved → closed`` для тикетов без активности ≥
    ``HELPDESK_RESOLVED_AUTO_CLOSE_DAYS`` (ТЗ §4.2, §8)."""
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=HELPDESK_RESOLVED_AUTO_CLOSE_DAYS)
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            update(HelpdeskTicket)
            .where(
                HelpdeskTicket.status == "resolved",
                HelpdeskTicket.last_activity_at < cutoff,
            )
            .values(
                status="closed",
                closed_at=datetime.now(UTC),
                closed_by_user_id=None,
            )
            .returning(HelpdeskTicket.id)
        )
        ids = res.scalars().all()
        if ids:
            await db.commit()
            logger.info("helpdesk.auto_closed", count=len(ids), ids=[str(i) for i in ids])
        return len(ids)


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


class _Suppress:
    def __enter__(self) -> _Suppress:
        return self

    def __exit__(self, *exc: object) -> bool:
        return True


__all__ = [
    "archive_closed_tickets_task",
    "auto_close_resolved_tickets",
    "cleanup_helpdesk_attachments_task",
    "create_next_helpdesk_archive_partition",
    "poll_helpdesk_mailbox",
]
