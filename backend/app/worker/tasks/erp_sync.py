"""ARQ-задачи ERP-синхронизации (docs/wip/erp-sync.md).

* :func:`run_erp_sync` — cron (каждые 15 мин). Module-gate (``erp_sync.enabled``)
  AND ``poll_enabled`` → interval-guard → distributed-lock → опрос ящика →
  :func:`run_import` на каждое подходящее письмо.
* :func:`erp_sync_watchdog` — cron (раз в день). Если последний успешный импорт
  старше ``expected_interval_days × 1.5`` → email + in-app алерт админам
  («письма от ERP не приходили с <дата>»).

Клон паттерна ``helpdesk``: распределённый lock через Redis ``SET NX EX`` +
Lua compare-and-delete; interval-guard через Redis-таймстамп (c bytes-decode
танцем — ARQ-воркер без ``decode_responses``).
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.erp_sync import ErpSyncRun, ErpSyncSettings
from app.services.erp_sync.importer import Attachment, attachment_hash, run_import
from app.services.erp_sync.mailbox import (
    LAST_POLL_KEY,
    LAST_SUCCESS_KEY,
    POLL_LOCK_KEY,
    POLL_LOCK_TTL,
    fetch_unread_attachments,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

WATCHDOG_LOCK_KEY = "erp_sync:watchdog:lock"
WATCHDOG_LOCK_TTL = 600  # 10 минут — watchdog лёгкий, но с запасом.

# Lua-скрипт атомарного compare-and-delete (клон helpdesk). Гарантирует, что
# воркер не удалёт чужой lock (например, если свой уже истёк по TTL и
# перехвачен другим воркером).
_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    """Захватить distributed lock. Возвращает токен или None (уже занят)."""
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    if not acquired:
        return None
    return token


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    """Освободить lock (best-effort, в finally с suppress)."""
    with suppress(Exception):
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]


async def _module_enabled(redis: Redis) -> bool:
    """Мастер-переключатель модуля (modules.json: erp_sync.enabled)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    return bool(modules.erp_sync.enabled)


async def _load_settings(db: AsyncSession) -> ErpSyncSettings | None:
    """Загрузить singleton настроек (id=1)."""
    return (
        await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()


async def run_erp_sync(ctx: dict, *, triggered_by: str = "cron") -> dict:
    """Опросить ящик ERP и импортировать каждое подходящее письмо.

    Вызывается cron'ом (``triggered_by='cron'``) или вручную через ARQ-job
    из ``POST /erp-sync/run`` (``triggered_by='manual'``).
    """
    redis: Redis | None = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    # Interval-guard только для cron-запуска (manual — всегда немедленно).
    async with AsyncSessionLocal() as db:
        settings = await _load_settings(db)
        if settings is None:
            return {"skipped": "not_configured"}

        if triggered_by == "cron":
            # Двойной гейтинг поллинга: poll_enabled отдельно от module.enabled.
            if not settings.poll_enabled:
                return {"skipped": "poll_disabled"}
            last = await redis.get(LAST_POLL_KEY)
            if last:
                if isinstance(last, bytes):
                    last = last.decode("utf-8", errors="ignore")
                try:
                    last_dt = datetime.fromisoformat(last)
                    if datetime.now(UTC) - last_dt < timedelta(
                        seconds=settings.poll_interval_seconds
                    ):
                        return {"skipped": "interval_not_elapsed"}
                except ValueError:
                    pass  # битое значение — игнорируем
        settings_row = settings

    # Для manual-запуска poll_enabled не проверяем (админ явно хочет «забрать
    # сейчас»), но IMAP должен быть настроен.
    if not settings_row.imap_host or not settings_row.imap_username:
        return {"skipped": "imap_not_configured"}

    lock_token = await _acquire_lock(redis, POLL_LOCK_KEY, POLL_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    await redis.set(LAST_POLL_KEY, datetime.now(UTC).isoformat())
    summary = {"processed": 0, "errors": 0}
    try:
        candidates = await fetch_unread_attachments(settings_row)
        for candidate, _uid in candidates:
            try:
                async with AsyncSessionLocal() as db:
                    await run_import(
                        db,
                        redis,
                        attachment=Attachment(
                            filename=candidate.filename,
                            data=candidate.data,
                            hash=attachment_hash(candidate.data),
                        ),
                        message_id=candidate.message_id,
                        triggered_by=triggered_by,
                    )
                summary["processed"] += 1
                await redis.set(LAST_SUCCESS_KEY, datetime.now(UTC).isoformat())
            except Exception:
                summary["errors"] += 1
                logger.exception("erp_sync.run.import_failed", message_id=candidate.message_id)
        if not candidates:
            logger.debug("erp_sync.run.no_new_mail")
    finally:
        await _release_lock(redis, POLL_LOCK_KEY, lock_token)

    logger.info("erp_sync.run.done", **summary)
    return summary


async def erp_sync_watchdog(ctx: dict) -> dict:
    """Раз в день: проверить, что ERP-отчёты приходят регулярно.

    Если последний успешный импорт старше ``expected_interval_days × 1.5``
    (или вообще не было) → email + in-app алерт админам. Защищает от случая
    «ERP перестал слать / письмо в спаме / сеть лежит» — без watchdog это
    заметят только когда кто-то зайдёт в профиль и увидит устаревшие данные.
    """
    redis: Redis | None = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    lock_token = await _acquire_lock(redis, WATCHDOG_LOCK_KEY, WATCHDOG_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    try:
        async with AsyncSessionLocal() as db:
            settings = await _load_settings(db)
            if settings is None or not settings.poll_enabled:
                return {"skipped": "poll_disabled"}

            # Последний успешный импорт (success или partial — оба означают,
            # что файл был получен и обработан).
            last_run = (
                await db.execute(
                    select(ErpSyncRun)
                    .where(ErpSyncRun.status.in_(("success", "partial")))
                    .order_by(ErpSyncRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            now = datetime.now(UTC)
            threshold = timedelta(days=settings.expected_interval_days * 1.5)

            if last_run is not None and last_run.finished_at is not None:
                last_finished = (
                    last_run.finished_at
                    if last_run.finished_at.tzinfo
                    else last_run.finished_at.replace(tzinfo=UTC)
                )
                if now - last_finished < threshold:
                    return {"ok": "recent_success"}
                stale_since = last_finished
            else:
                stale_since = None  # ни одного успешного импорта не было

        await _send_watchdog_alert(redis, settings=settings, stale_since=stale_since)
        return {"alerted": True, "stale_since": stale_since.isoformat() if stale_since else None}
    finally:
        await _release_lock(redis, WATCHDOG_LOCK_KEY, lock_token)


async def _send_watchdog_alert(
    redis: Redis, *, settings: ErpSyncSettings, stale_since: datetime | None
) -> None:
    """Email + in-app алерт админам о пропуске ERP-отчётов.

    Best-effort: отдельная транзакция, не афректит бизнес-данные. Если алерт
    упадёт — не критично (watchdog сработает снова на следующий день).
    """

    from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email
    from app.services.erp_sync.recipients import get_admin_user_ids, get_report_emails
    from app.services.notifications import create_notification

    when = stale_since.strftime("%d.%m.%Y %H:%M") if stale_since else "никогда"
    subject = "⚠ ERP-синхронизация: отчёты не приходят"
    html_body = (
        '<div style="font-family:Arial,sans-serif;color:#24292f;line-height:1.5">'
        f"<p>Последний успешный импорт ERP-выгрузки: <strong>{when}</strong>.</p>"
        "<p>Это превышает ожидаемый интервал. Возможные причины:</p>"
        "<ul>"
        "<li>ERP-система перестала слать отчёты по расписанию;</li>"
        "<li>письмо попало в спам/другую папку;</li>"
        "<li>сеть/IMAP-ящик недоступен.</li>"
        "</ul>"
        "<p>Проверьте настройки ERP-синхронизации в админке и очередь писем.</p>"
        "</div>"
    )
    plain = f"Последний успешный импорт: {when}. Превышен ожидаемый интервал."

    publish_callbacks: list = []
    try:
        async with AsyncSessionLocal() as db:
            emails = await get_report_emails(db, settings)
            for email in emails:
                await enqueue_outbox_email(
                    db,
                    kind=KIND_GENERIC,
                    to_email=email,
                    subject=subject,
                    body_html=html_body,
                    body_text=plain,
                    payload={"erp_sync_watchdog": True},
                    related_resource_type="erp_sync_watchdog",
                )
            admin_ids = await get_admin_user_ids(db)
            for uid in admin_ids:
                publish = await create_notification(
                    db,
                    redis,
                    user_id=uid,
                    type="erp_sync_watchdog",
                    title=subject,
                    body="Отчёты ERP не приходят дольше ожидаемого интервала.",
                    link="/admin?tab=erp_sync",
                )
                publish_callbacks.append(publish)
            await db.commit()
        for publish in publish_callbacks:
            with suppress(Exception):
                await publish()
    except Exception:
        logger.exception("erp_sync.watchdog.alert_failed")


# ── Integration health probe (вызывается из integration_health.probe_integrations) ─


async def probe_erp_sync() -> bool | None:
    """Свежесть ERP-синхронизации для health-дашборда.

    Возвращает:

    * ``None`` — модуль выключен или не настроен (нет точки данных);
    * ``True`` — последний импорт свежий (в пределах expected_interval × 1.5);
    * ``False`` — протух / ошибок / ни одного успешного импорта.

    Никогда не бросает — оборачиваем в try/except (контракт probe-функций).
    """
    from app.core.modules_config import load_modules

    try:
        if not load_modules().erp_sync.enabled:
            return None
    except Exception:
        return None

    try:
        async with AsyncSessionLocal() as db:
            settings = await _load_settings(db)
            if settings is None or not settings.poll_enabled:
                return None
            last_run = (
                await db.execute(
                    select(ErpSyncRun)
                    .where(ErpSyncRun.status.in_(("success", "partial")))
                    .order_by(ErpSyncRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_run is None:
                return False
            finished = last_run.finished_at
            if finished is None:
                return False
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=UTC)
            threshold = timedelta(days=settings.expected_interval_days * 1.5)
            return datetime.now(UTC) - finished < threshold
    except Exception as exc:
        logger.warning("erp_sync.probe_failed", error=str(exc))
        return False
