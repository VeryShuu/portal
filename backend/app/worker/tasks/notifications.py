"""ARQ задачи для уведомлений: отправка email, триггеры по событиям."""

from __future__ import annotations

from arq import Retry

from app.core.logging import get_logger
from app.worker.tasks.email_utils import (
    JOB_TIMEOUT_SECONDS,
    MAX_TRIES,
    classify_smtp_error,
    compute_retry_defer,
    load_smtp_config,
    smtp_send,
)

logger = get_logger(__name__)


async def send_email_notification(
    ctx: dict,
    *,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> bool:
    """Отправляет email через aiosmtplib с управляемым retry через ARQ."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg = load_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"] or "portal@company.local"
    msg["To"] = to_email

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    job_try = int(ctx.get("job_try") or 1)

    try:
        await smtp_send(msg, cfg)
        logger.info("email.sent", to=to_email, subject=subject)
        return True
    except Exception as exc:
        error_class = classify_smtp_error(exc)
        error_type = type(exc).__name__
        logger.exception(
            "email.send_failed",
            error=str(exc),
            error_type=error_type,
            error_class=error_class,
            job_try=job_try,
            to=to_email,
        )
        if error_class == "permanent" or job_try >= MAX_TRIES:
            raise
        defer = compute_retry_defer(job_try, error_class)
        raise Retry(defer=defer) from exc


send_email_notification.max_tries = MAX_TRIES  # type: ignore[attr-defined]
send_email_notification.job_timeout = JOB_TIMEOUT_SECONDS  # type: ignore[attr-defined]


async def notify_news_published(
    ctx: dict,
    *,
    news_id: str,
    news_title: str,
    target_departments: list[str] | None = None,
    target_roles: list[str] | None = None,
) -> int:
    """Триггерит in-app SSE-уведомления о новой новости.

    Автоматическая email-рассылка по новостям отключена намеренно: письма о
    новостях отправляются только вручную через кнопку «поделиться»
    (``app.services.news.email_share.share_news_by_email``).
    """
    import uuid as _uuid

    from app.core.database import AsyncSessionLocal
    from app.services.notifications import notify_users_news_published

    redis = ctx.get("redis")
    if redis is None:
        return 0

    try:
        async with AsyncSessionLocal() as db:
            sent = await notify_users_news_published(
                db,
                redis,
                news_id=_uuid.UUID(news_id),
                news_title=news_title,
                target_departments=target_departments,
                target_roles=target_roles,
            )
    except Exception as exc:
        logger.exception("notifications.inapp_news_failed", news_id=news_id, error=str(exc))
        return 0

    logger.info("notifications.news_inapp_sent", news_id=news_id, sent=sent)
    return sent


async def cleanup_notifications(ctx: dict) -> int:
    """Удаляет старые уведомления по retention-настройкам (политика C).

    Читает ``notifications_read_retention_days`` / ``notifications_unread_retention_days``
    из system_config при каждом запуске (свежие настройки без рестарта воркера).
    Обе ветки ``<= 0`` → задача полностью отключена (early return 0). Транзакция
    охватывает оба DELETE; ``AsyncSessionLocal`` и ``load_system_settings`` импортируются
    лениво (разрыв import-cycle, как в ``notify_news_published``).
    """
    from app.core.database import AsyncSessionLocal
    from app.core.system_config import load_system_settings
    from app.services.notifications import cleanup_old_notifications

    cfg = load_system_settings()
    read_days = cfg.notifications_read_retention_days
    unread_days = cfg.notifications_unread_retention_days

    if read_days <= 0 and unread_days <= 0:
        logger.info("notifications.cleanup.disabled", reason="retention_days_le_0")
        return 0

    async with AsyncSessionLocal() as db, db.begin():
        stats = await cleanup_old_notifications(
            db,
            read_retention_days=read_days,
            unread_retention_days=unread_days,
        )

    logger.info("notifications.cleanup.done", **stats)
    return stats["read_deleted"] + stats["unread_deleted"]
