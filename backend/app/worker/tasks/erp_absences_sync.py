"""ARQ-задачи ERP-синхронизации отсутствий (второй поток).

Клон :mod:`erp_sync` (поток дней рождения). Тот же общий IMAP-ящик (ADR-048),
но:

* свой distributed-lock и interval-guard (независимые Redis-ключи);
* per-потоковый гейтинг ``absences_poll_enabled`` (общий ``modules.erp_sync.enabled``
  + общий ``poll_interval_seconds``);
* свои фильтры писем (``mail_absences_*``) — письмо от ERP с отчётом отсутствий
  приходит отдельно от справочника сотрудников;
* свой watchdog (``absences_expected_interval_days``) и probe.

Общие с днями рождения: module-gate, IMAP-настройки, ``delete_after_fetch``.
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
from app.models.erp_sync import ErpAbsencesRun, ErpSyncSettings
from app.services.email_settings import imap_configured, load_email_settings
from app.services.erp_sync.absences_importer import (
    AbsenceAttachment,
    absence_attachment_hash,
    run_absences_import,
)
from app.services.erp_sync.mailbox import (
    MailFilters,
    delete_messages,
    fetch_unread_attachments,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

# Независимые Redis-ключи (не делим с днями рождения — иначе блокировали бы друг друга).
LAST_POLL_KEY = "erp_absences:imap:last_poll_at"
POLL_LOCK_KEY = "erp_absences:imap:poll_lock"
POLL_LOCK_TTL = 300  # 5 минут — как у дней рождения.
LAST_SUCCESS_KEY = "erp_absences:last_success_at"

WATCHDOG_LOCK_KEY = "erp_absences:watchdog:lock"
WATCHDOG_LOCK_TTL = 600

# Lua-скрипт атомарного compare-and-delete (клон erp_sync).
_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    if not acquired:
        return None
    return token


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    with suppress(Exception):
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]


async def _module_enabled(redis: Redis) -> bool:
    """Мастер-переключатель модуля (modules.json: erp_sync.enabled) — общий с днями рождения."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    return bool(modules.erp_sync.enabled)


async def _load_settings(db: AsyncSession) -> ErpSyncSettings | None:
    return (
        await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()


async def run_erp_absences_sync(ctx: dict, *, triggered_by: str = "cron") -> dict:
    """Опросить ящик ERP и импортировать отчёт отсутствий.

    Вызывается cron'ом (``triggered_by='cron'``) или вручную через ARQ-job из
    ``POST /erp-sync/absences/run`` (``triggered_by='manual'``).
    """
    redis: Redis | None = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    # Interval-guard только для cron-запуска (manual — всегда немедленно).
    # poll_interval_seconds — общий с днями рождения (частота опроса ящика).
    async with AsyncSessionLocal() as db:
        settings = await _load_settings(db)
        if settings is None:
            return {"skipped": "not_configured"}

        if triggered_by == "cron":
            # Двойной гейтинг: общий module.enabled + per-потоковый absences_poll_enabled.
            if not settings.absences_poll_enabled:
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

    # Для manual-запуска absences_poll_enabled не проверяем (админ явно хочет
    # «забрать сейчас»), но общий IMAP должен быть настроен.
    email_settings = load_email_settings()
    if not imap_configured(email_settings):
        return {"skipped": "imap_not_configured"}

    lock_token = await _acquire_lock(redis, POLL_LOCK_KEY, POLL_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    await redis.set(LAST_POLL_KEY, datetime.now(UTC).isoformat())
    summary = {"processed": 0, "errors": 0, "deleted": 0}
    try:
        # Фильтры писём — per-потоковые (письмо с отчётом отсутствий отдельное).
        filters = MailFilters(
            subject_filter=settings_row.mail_absences_subject_filter,
            sender_filter=settings_row.mail_absences_sender_filter,
            attachment_filter=settings_row.mail_absences_attachment_filter,
        )
        candidates = await fetch_unread_attachments(email_settings, filters)
        processed_uids: list[str] = []
        for candidate, uid in candidates:
            try:
                async with AsyncSessionLocal() as db:
                    await run_absences_import(
                        db,
                        redis,
                        attachment=AbsenceAttachment(
                            filename=candidate.filename,
                            data=candidate.data,
                            hash=absence_attachment_hash(candidate.data),
                        ),
                        message_id=candidate.message_id,
                        triggered_by=triggered_by,
                    )
                summary["processed"] += 1
                processed_uids.append(uid)
                await redis.set(LAST_SUCCESS_KEY, datetime.now(UTC).isoformat())
            except Exception:
                summary["errors"] += 1
                logger.exception("erp_absences.run.import_failed", message_id=candidate.message_id)
        if not candidates:
            logger.debug("erp_absences.run.no_new_mail")
        # delete_after_fetch — общий с днями рождения (чистка общего ящика).
        if settings_row.delete_after_fetch and processed_uids:
            try:
                summary["deleted"] = await delete_messages(email_settings, processed_uids)
            except Exception:
                logger.exception("erp_absences.run.delete_failed", uids=processed_uids)
    finally:
        await _release_lock(redis, POLL_LOCK_KEY, lock_token)

    logger.info("erp_absences.run.done", **summary)
    return summary


async def erp_absences_watchdog(ctx: dict) -> dict:
    """Раз в день: проверить, что отчёты отсутствий приходят регулярно.

    Если последний успешный импорт старше ``absences_expected_interval_days × 1.5``
    (или вообще не было) → email + in-app алерт админам.
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
            if settings is None or not settings.absences_poll_enabled:
                return {"skipped": "poll_disabled"}

            last_run = (
                await db.execute(
                    select(ErpAbsencesRun)
                    .where(ErpAbsencesRun.status.in_(("success", "partial")))
                    .order_by(ErpAbsencesRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            now = datetime.now(UTC)
            threshold = timedelta(days=settings.absences_expected_interval_days * 1.5)

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
                stale_since = None

        await _send_watchdog_alert(redis, settings=settings, stale_since=stale_since)
        return {
            "alerted": True,
            "stale_since": stale_since.isoformat() if stale_since else None,
        }
    finally:
        await _release_lock(redis, WATCHDOG_LOCK_KEY, lock_token)


async def _send_watchdog_alert(
    redis: Redis, *, settings: ErpSyncSettings, stale_since: datetime | None
) -> None:
    """Email + in-app алерт админам о пропуске отчётов отсутствий. Best-effort."""
    from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email
    from app.services.erp_sync.recipients import get_admin_user_ids, get_report_emails
    from app.services.notifications import create_notification

    when = stale_since.strftime("%d.%m.%Y %H:%M") if stale_since else "никогда"
    subject = "⚠ ERP-отсутствия: отчёты не приходят"
    html_body = (
        '<div style="font-family:Arial,sans-serif;color:#24292f;line-height:1.5">'
        f"<p>Последний успешный импорт отчёта отсутствий: <strong>{when}</strong>.</p>"
        "<p>Это превышает ожидаемый интервал. Возможные причины:</p>"
        "<ul>"
        "<li>ERP-система перестала слать отчёты отсутствий по расписанию;</li>"
        "<li>письмо попало в спам/другую папку;</li>"
        "<li>сеть/IMAP-ящик недоступен.</li>"
        "</ul>"
        "<p>Проверьте настройки ERP-синхронизации в админке.</p>"
        "</div>"
    )
    plain = f"Последний успешный импорт отсутствий: {when}. Превышен ожидаемый интервал."

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
                    payload={"erp_absences_watchdog": True},
                    related_resource_type="erp_absences_watchdog",
                )
            admin_ids = await get_admin_user_ids(db)
            for uid in admin_ids:
                publish = await create_notification(
                    db,
                    redis,
                    user_id=uid,
                    type="erp_absences_watchdog",
                    title=subject,
                    body="Отчёты отсутствий ERP не приходят дольше ожидаемого интервала.",
                    link="/admin?tab=erp_sync",
                )
                publish_callbacks.append(publish)
            await db.commit()
        for publish in publish_callbacks:
            with suppress(Exception):
                await publish()
    except Exception:
        logger.exception("erp_absences.watchdog.alert_failed")


# ── Integration health probe ────────────────────────────────────────────────


async def probe_erp_absences() -> bool | None:
    """Свежесть потока отсутствий для health-дашборда (клон probe_erp_sync).

    * ``None`` — модуль выключен или absence-поллинг отключён;
    * ``True`` — последний импорт свежий (в пределах expected_interval × 1.5);
    * ``False`` — протух / ошибок / ни одного успешного импорта.
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
            if settings is None or not settings.absences_poll_enabled:
                return None
            last_run = (
                await db.execute(
                    select(ErpAbsencesRun)
                    .where(ErpAbsencesRun.status.in_(("success", "partial")))
                    .order_by(ErpAbsencesRun.started_at.desc())
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
            threshold = timedelta(days=settings.absences_expected_interval_days * 1.5)
            return datetime.now(UTC) - finished < threshold
    except Exception as exc:
        logger.warning("erp_absences.probe_failed", error=str(exc))
        return False
