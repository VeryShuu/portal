"""ARQ-задачи интеграции Directum (docs/directum.md).

* :func:`run_directum_sync` — cron (ежечасно в :17). Module-gate
  (``modules.directum.enabled``) AND ``settings.enabled`` AND (для cron)
  ``overdue_enabled`` AND «текущий московский час ∈ overdue_run_hours» AND
  «в этом часе ещё не запускали» → distributed-lock → сервисный прогон
  (:func:`app.services.directum.sync.run_directum_sync`).
* :func:`directum_watchdog` — cron (раз в день). Если последний успешный прогон
  старше ``expected_interval_days × 1.5`` → email + in-app алерт админам.
* :func:`probe_directum` — свежесть для health-дашборда интеграций.

Расписание (миграция 099): часы задаются в московском времени (+03:00, как у
самого Directum); cron тикает по UTC в :17 каждого часа — минута запуска
всегда 17-я. Клон паттерна ``erp_sync`` по локу (Redis ``SET NX EX`` + Lua
compare-and-delete); дедуп «один прогон в час» — Redis-ключ с строкой
``YYYY-MM-DD HH`` (bytes-decode — ARQ-воркер без ``decode_responses``).
Skip-причины run-строку не создают.
"""

from __future__ import annotations

import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.directum import DirectumRun, DirectumSettings
from app.services.directum.sync import (
    directum_configured,
)

# Имя воркер-задачи совпадает с именем сервисной функции — импортируем с
# алиасом, иначе F811-затенение превратило бы вызов в рекурсию.
from app.services.directum.sync import run_directum_sync as run_directum_sync_service

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

# Часы расписания админ задаёт по московскому времени; РФ без перевода часов,
# поэтому фиксированное смещение надёжнее zoneinfo (tzdata в slim-образах нет).
SCHEDULE_TZ = timezone(timedelta(hours=3))

LAST_RUN_HOUR_KEY = "directum:last_run_hour"
LAST_RUN_HOUR_TTL = 48 * 3600  # хватит на дедуп любого часа вчерашнего дня.
LAST_SUCCESS_KEY = "directum:last_success_at"
POLL_LOCK_KEY = "directum:poll_lock"
POLL_LOCK_TTL = 600  # прогон = один OData-запрос + enqueue; 10 мин с запасом.
WATCHDOG_LOCK_KEY = "directum:watchdog:lock"
WATCHDOG_LOCK_TTL = 600

# Lua-скрипт атомарного compare-and-delete (клон erp_sync): воркер не удаляет
# чужой lock (свой истёк по TTL и перехвачен другим воркером).
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
    with suppress(Exception):
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]


async def _module_enabled(redis: Redis) -> bool:
    """Мастер-переключатель модуля (modules.json: directum.enabled)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    return bool(modules.directum.enabled)


async def _load_settings(db: AsyncSession) -> DirectumSettings | None:
    return (
        await db.execute(select(DirectumSettings).where(DirectumSettings.id == 1))
    ).scalar_one_or_none()


def _schedule_now() -> tuple[int, str]:
    """Текущий час расписания (московский) и ключ дедупа ``YYYY-MM-DD HH``."""
    now_local = datetime.now(SCHEDULE_TZ)
    return now_local.hour, now_local.strftime("%Y-%m-%d %H")


async def run_directum_sync(ctx: dict, *, triggered_by: str = "cron") -> dict:
    """Прогон «Просроченные задачи»: fetch OData → матчинг → уведомления.

    Вызывается cron'ом (``triggered_by='cron'``) или вручную через ARQ-job из
    ``POST /directum/run`` (``triggered_by='manual'`` — обходит overdue_enabled
    и расписание, но не мастер-гейты).
    """
    redis: Redis | None = ctx.get("redis")
    if redis is None or not await _module_enabled(redis):
        return {"skipped": "module_disabled"}

    hour_key: str = ""
    async with AsyncSessionLocal() as db:
        settings = await _load_settings(db)
        if settings is None:
            return {"skipped": "not_configured"}
        if not settings.enabled:
            return {"skipped": "disabled"}
        if not directum_configured(settings):
            return {"skipped": "not_configured"}

        # Расписание + per-задачный гейтинг — только для cron (manual —
        # всегда немедленно; правило «уведомлять каждый прогон» работает и для
        # ручных запусков).
        if triggered_by == "cron":
            if not settings.overdue_enabled:
                return {"skipped": "overdue_disabled"}
            hour, hour_key = _schedule_now()
            if hour not in (settings.overdue_run_hours or []):
                return {"skipped": "not_scheduled_hour"}
            last = await redis.get(LAST_RUN_HOUR_KEY)
            if last:
                if isinstance(last, bytes):
                    last = last.decode("utf-8", errors="ignore")
                if last == hour_key:
                    return {"skipped": "already_ran_this_hour"}

    lock_token = await _acquire_lock(redis, POLL_LOCK_KEY, POLL_LOCK_TTL)
    if lock_token is None:
        return {"skipped": "lock_held"}

    if hour_key:
        await redis.set(LAST_RUN_HOUR_KEY, hour_key, ex=LAST_RUN_HOUR_TTL)
    try:
        async with AsyncSessionLocal() as db:
            run = await run_directum_sync_service(db, triggered_by=triggered_by)
        if run.status in ("success", "partial"):
            await redis.set(LAST_SUCCESS_KEY, datetime.now(UTC).isoformat())
        summary = {
            "run_id": run.id,
            "status": run.status,
            "tasks": run.tasks_total,
            "notified": run.users_notified,
        }
    finally:
        await _release_lock(redis, POLL_LOCK_KEY, lock_token)

    logger.info("directum.worker.run_done", **summary)
    return summary


async def directum_watchdog(ctx: dict) -> dict:
    """Раз в день: проверить, что прогоны Directum случаются регулярно.

    Если последний успешный прогон старше ``expected_interval_days × 1.5``
    (или успешных не было) → email + in-app алерт админам. Ловит случаи
    «Directum лежит / креды протухли / cron-пол заблокирован».
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
            if settings is None or not settings.enabled or not settings.overdue_enabled:
                return {"skipped": "disabled"}

            last_run = (
                await db.execute(
                    select(DirectumRun)
                    .where(DirectumRun.status.in_(("success", "partial")))
                    .order_by(DirectumRun.started_at.desc())
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
                stale_since = None  # ни одного успешного прогона не было

        await _send_watchdog_alert(redis, settings=settings, stale_since=stale_since)
        return {"alerted": True, "stale_since": stale_since.isoformat() if stale_since else None}
    finally:
        await _release_lock(redis, WATCHDOG_LOCK_KEY, lock_token)


async def _send_watchdog_alert(
    redis: Redis, *, settings: DirectumSettings, stale_since: datetime | None
) -> None:
    """Email + in-app алерт админам (best-effort, отдельная транзакция)."""

    from app.services.directum.recipients import get_admin_user_ids, get_report_emails
    from app.services.email_outbox import KIND_DIRECTUM, enqueue_outbox_email
    from app.services.notifications import create_notification

    when = stale_since.strftime("%d.%m.%Y %H:%M") if stale_since else "никогда"
    subject = "⚠ Directum: прогоны не выполняются"
    html_body = (
        '<div style="font-family:Arial,sans-serif;color:#24292f;line-height:1.5">'
        f"<p>Последний успешный прогон «Просроченные задачи»: <strong>{when}</strong>.</p>"
        "<p>Это превышает ожидаемый интервал. Возможные причины:</p>"
        "<ul>"
        "<li>Directum (sed.mage.ru) недоступен или креды сервисной учётки протухли;</li>"
        "<li>модуль выключен (переключатель в настройках Directum);</li>"
        "<li>сеть/TLS недоступны.</li>"
        "</ul>"
        "<p>Проверьте вкладку Directum в админке (кнопка «Проверить подключение»).</p>"
        "</div>"
    )
    plain = f"Последний успешный прогон: {when}. Превышен ожидаемый интервал."

    publish_callbacks: list = []
    try:
        async with AsyncSessionLocal() as db:
            emails = await get_report_emails(db, settings)
            for email in emails:
                await enqueue_outbox_email(
                    db,
                    kind=KIND_DIRECTUM,
                    to_email=email,
                    subject=subject,
                    body_html=html_body,
                    body_text=plain,
                    payload={"directum_watchdog": True},
                    related_resource_type="directum_watchdog",
                )
            admin_ids = await get_admin_user_ids(db)
            for uid in admin_ids:
                publish = await create_notification(
                    db,
                    redis,
                    user_id=uid,
                    type="directum_watchdog",
                    title=subject,
                    body="Прогоны Directum не выполняются дольше ожидаемого интервала.",
                    link="/admin?tab=directum",
                )
                publish_callbacks.append(publish)
            await db.commit()
        for publish in publish_callbacks:
            with suppress(Exception):
                await publish()
    except Exception:
        logger.exception("directum.watchdog.alert_failed")


# ── Integration health probe (вызывается из integration_health.probe_integrations) ─


async def probe_directum() -> bool | None:
    """Свежесть прогонов Directum для health-дашборда.

    ``None`` — модуль выключен/не настроен (нет точки данных); ``True`` —
    последний прогон свежий; ``False`` — протух / ошибок / не было успехов.
    """
    from app.core.modules_config import load_modules

    try:
        if not load_modules().directum.enabled:
            return None
    except Exception:
        return None

    try:
        async with AsyncSessionLocal() as db:
            settings = await _load_settings(db)
            if settings is None or not settings.enabled or not settings.overdue_enabled:
                return None
            last_run = (
                await db.execute(
                    select(DirectumRun)
                    .where(DirectumRun.status.in_(("success", "partial")))
                    .order_by(DirectumRun.started_at.desc())
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
        logger.warning("directum.probe_failed", error=str(exc))
        return False
