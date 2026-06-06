"""ARQ-задачи для transactional email outbox.

`process_email_outbox` — основной диспетчер, запускается каждые несколько секунд:
   1. Атомарно захватывает PENDING-записи (FOR UPDATE SKIP LOCKED).
   2. Для каждой строит MIME и шлёт через aiosmtplib.
   3. По результату обновляет outbox-строку (SENT / PENDING+next_attempt_at / DLQ).

`cleanup_email_outbox` — раз в сутки чистит старые SENT записи.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.email_outbox import (
    KIND_MEETING,
    claim_pending,
    cleanup_old_sent,
    decode_ical_bytes,
    mark_failed,
    mark_sent,
    requeue_stale_sending,
)
from app.worker.tasks.email_utils import (
    classify_smtp_error,
    load_smtp_config,
    smtp_send,
)

logger = get_logger(__name__)

DISPATCH_BATCH_SIZE = 20
STALE_SENDING_TIMEOUT_SECONDS = 600


async def process_email_outbox(ctx: dict) -> int:
    """Обрабатывает очередную пачку PENDING писем. Возвращает кол-во отправленных."""
    sent_ok = 0
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await requeue_stale_sending(
                    session, older_than_seconds=STALE_SENDING_TIMEOUT_SECONDS
                )
                claimed = await claim_pending(session, limit=DISPATCH_BATCH_SIZE)
            if not claimed:
                return 0

            cfg = load_smtp_config()
            smtp_configured = bool(cfg.get("host"))
            if not smtp_configured:
                logger.warning("email_outbox.dispatch.smtp_not_configured", claimed=len(claimed))

            for row in claimed:
                if not smtp_configured:
                    async with session.begin():
                        await mark_failed(
                            session,
                            row["id"],
                            error="SMTP host is not configured",
                            error_type="ConfigurationError",
                            error_class="transient",
                            current_attempts=row["attempts"],
                            max_attempts=row["max_attempts"],
                        )
                    continue

                try:
                    msg = _build_mime(row, cfg)
                    await smtp_send(msg, cfg)
                except Exception as exc:
                    error_class = classify_smtp_error(exc)
                    error_type = type(exc).__name__
                    logger.exception(
                        "email_outbox.send_failed",
                        outbox_id=str(row["id"]),
                        kind=row["kind"],
                        to=row["to_email"],
                        error=str(exc),
                        error_type=error_type,
                        error_class=error_class,
                        attempts=row["attempts"],
                    )
                    async with session.begin():
                        await mark_failed(
                            session,
                            row["id"],
                            error=str(exc),
                            error_type=error_type,
                            error_class=error_class,
                            current_attempts=row["attempts"],
                            max_attempts=row["max_attempts"],
                        )
                    continue

                async with session.begin():
                    await mark_sent(session, row["id"])
                sent_ok += 1
                logger.info(
                    "email_outbox.sent",
                    outbox_id=str(row["id"]),
                    kind=row["kind"],
                    to=row["to_email"],
                )
    except Exception as exc:
        logger.exception("email_outbox.dispatch_failed", error=str(exc))
    return sent_ok


async def cleanup_email_outbox(ctx: dict) -> int:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            deleted = await cleanup_old_sent(session, older_than_days=30)
        logger.info("email_outbox.cleanup", deleted=deleted)
        return deleted


def _build_mime(row: dict, cfg: dict) -> MIMEMultipart:
    kind = row["kind"]
    to_email = row["to_email"]
    subject = row["subject"]
    body_html = row["body_html"] or ""
    body_text = row["body_text"]
    payload = row["payload"] or {}

    if kind == KIND_MEETING:
        outer = MIMEMultipart("mixed")
        outer["Subject"] = subject
        outer["From"] = cfg["from_address"] or "portal@company.local"
        outer["To"] = to_email
        outer["Content-Class"] = "urn:content-classes:calendarmessage"

        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body_html, "html", "utf-8"))

        ical_b64 = payload.get("ical_b64") or ""
        method = payload.get("method") or "REQUEST"
        if ical_b64:
            ical_bytes = decode_ical_bytes(ical_b64)
            ical_inline = MIMEText(ical_bytes.decode("utf-8"), "calendar", "utf-8")
            ical_inline.set_param("method", method)
            ical_inline.set_param("charset", "UTF-8")
            alternative.attach(ical_inline)

        outer.attach(alternative)
        return outer

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"] or "portal@company.local"
    msg["To"] = to_email
    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    return msg


__all__ = ["cleanup_email_outbox", "process_email_outbox"]
