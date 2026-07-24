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
from app.services.helpdesk.drafts import cleanup_expired_drafts
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

# Lock для archive-семейства (archive/partition/cleanup). Раньше эти cron
# брали отдельные lock'и: ``archive_closed_tickets`` делал SELECT без
# ``FOR UPDATE SKIP LOCKED``, и при двух воркерах оба выбирали одни и те же
# ``closed``-тикеты до commit → двойная архивация / гонка на ``delete_ticket_dir``.
# Партиционный cron идемпотентен (``CREATE TABLE IF NOT EXISTS``), cleanup
# best-effort — но lock'и продублированы для единообразия и защиты FS-операций.
ARCHIVE_LOCK_KEY = "helpdesk:archive:lock"
ARCHIVE_LOCK_TTL = 600  # 10 минут — архивация может быть долгой при большом backlog.
PARTITION_LOCK_KEY = "helpdesk:partition:lock"
PARTITION_LOCK_TTL = 120  # 2 минуты — DDL-операции быстрые.
CLEANUP_LOCK_KEY = "helpdesk:cleanup:lock"
CLEANUP_LOCK_TTL = 600  # 10 минут — rmtree по многим папкам может занять время.
# Отдельный lock для cleanup draft-attachments (orphan-черновики форм создания
# заявки, не отправленных в течение TTL). FS-операции простые (unlink), но lock
# дублирован для единообразия с остальным cleanup-семейством и защиты от гонок.
DRAFT_CLEANUP_LOCK_KEY = "helpdesk:cleanup-drafts:lock"
DRAFT_CLEANUP_LOCK_TTL = 120  # 2 минуты — unlink'и быстрые.


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    """Взять distributed lock по образцу poll_lock/digest_lock.

    Возвращает ``lock_token`` при успехе или ``None``, если лок уже занят другим
    воркером. Release — через ``_release_lock`` (Lua-скрипт с проверкой токена,
    чтобы не удалить чужой лок)."""
    token = secrets.token_hex(16)
    # ``redis.set(..., nx=True)`` возвращает ``True`` при успехе и ``None`` при
    # занятом локе; проверка ``if not acquired`` используется по всему проекту
    # (audit/files). Возвращаем только что сгенерированный ``token`` — он же
    # идёт в Lua-release для атомарной проверки владения.
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    if not acquired:
        return None
    return token


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    """Освободить distributed lock (атомарная проверка token → delete).

    ``suppress(Exception)`` — release в ``finally``: неудачный release не должен
    ронять воркер (лок истечёт по TTL сам)."""
    with suppress(Exception):
        # ``redis.asyncio.Redis.eval`` асинхронен, но в stub'е redis-py имеет
        # перегрузку, возвращающую ``Awaitable[str] | str`` → mypy-error на
        # ``await``. Локальное игнорирование чистее, чем ``cast("Any", ...)``
        # на каждом вызове (poll_lock/digest_lock в тех же задачах обходят это
        # тем, что ``redis = ctx.get(...)`` без аннотации = ``Any``).
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]  # redis-py async-overload typing


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
    lock_token = await _acquire_lock(redis, POLL_LOCK_KEY, POLL_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}
    try:
        await redis.set(LAST_POLL_KEY, datetime.now(UTC).isoformat())
        async with AsyncSessionLocal() as db:
            return await poll_mailbox(db, redis, settings_row=settings_row)
    finally:
        await _release_lock(redis, POLL_LOCK_KEY, lock_token)


# ---------------------------------------------------------------------------
# Archive + partition + cleanup
# ---------------------------------------------------------------------------


async def archive_closed_tickets_task(ctx: dict) -> int:
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    # Distributed lock: ``archive_closed_tickets`` читает ``closed``-тикеты без
    # ``FOR UPDATE SKIP LOCKED`` → без лока два воркера продублируют работу.
    lock_token = await _acquire_lock(redis, ARCHIVE_LOCK_KEY, ARCHIVE_LOCK_TTL)
    if lock_token is None:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            return await archive_closed_tickets(db)
    finally:
        await _release_lock(redis, ARCHIVE_LOCK_KEY, lock_token)


async def create_next_helpdesk_archive_partition(ctx: dict) -> str:
    """Создать месячные партиции архива (run_at_startup + ежемесячно)."""
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return ""
    # Lock дублирован для единообразия; сам ``CREATE TABLE IF NOT EXISTS``
    # идемпотентен, но параллельный ``conn.execute`` мог бы гоняться на pg_class.
    lock_token = await _acquire_lock(redis, PARTITION_LOCK_KEY, PARTITION_LOCK_TTL)
    if lock_token is None:
        return ""
    try:
        pg_url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(pg_url, statement_cache_size=0)
        try:
            created = await ensure_helpdesk_archive_partitions(conn, months_ahead=3)
            logger.info("helpdesk.archive.partitions_created", tables=created)
            return str(created)
        finally:
            await conn.close()
    finally:
        await _release_lock(redis, PARTITION_LOCK_KEY, lock_token)


async def cleanup_helpdesk_attachments_task(ctx: dict) -> int:
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    # Lock: ``cleanup_archived_files`` делает ``rmtree`` по папкам тикетов —
    # гонка двух воркеров на одном тикете не страшна (``ignore_errors=True``),
    # но лишние FS-операции и шум в логах ни к чему.
    lock_token = await _acquire_lock(redis, CLEANUP_LOCK_KEY, CLEANUP_LOCK_TTL)
    if lock_token is None:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            return await cleanup_archived_files(db)
    finally:
        await _release_lock(redis, CLEANUP_LOCK_KEY, lock_token)


async def cleanup_expired_drafts_task(ctx: dict) -> int:
    """Удалить draft-attachments старше ``HELPDESK_DRAFT_TTL_HOURS``.

    Draft-файлы создаются формой создания заявки (``POST /draft-attachments``);
    если юзер не отправил заявку (закрыл вкладку, отвлёкся), файлы + строки
    остаются orphan'ами. Cron чистит их раз в час — симметрично с
    ``cleanup_helpdesk_attachments_task`` для архивных файлов.
    """
    redis = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return 0
    lock_token = await _acquire_lock(redis, DRAFT_CLEANUP_LOCK_KEY, DRAFT_CLEANUP_LOCK_TTL)
    if lock_token is None:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            removed = await cleanup_expired_drafts(db)
            if removed:
                await db.commit()
            return removed
    finally:
        await _release_lock(redis, DRAFT_CLEANUP_LOCK_KEY, lock_token)


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
    lock_token = await _acquire_lock(redis, DIGEST_LOCK_KEY, DIGEST_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}
    try:
        portal_base_url = load_system_settings().portal_base_url
        async with AsyncSessionLocal() as db:
            return await send_digests(db, redis, portal_base_url=portal_base_url, now=now)
    finally:
        await _release_lock(redis, DIGEST_LOCK_KEY, lock_token)


__all__ = [
    "ARCHIVE_LOCK_KEY",
    "CLEANUP_LOCK_KEY",
    "DIGEST_LOCK_KEY",
    "PARTITION_LOCK_KEY",
    "POLL_LOCK_KEY",
    "archive_closed_tickets_task",
    "cleanup_helpdesk_attachments_task",
    "create_next_helpdesk_archive_partition",
    "poll_helpdesk_mailbox",
    "send_helpdesk_digest",
]
# Прим.: lock-keys (верхний регистр) и ARQ-задачи (snake_case) отсортированы
# вместе по умолчанию RUF022 (isort-style).
