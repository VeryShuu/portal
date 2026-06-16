"""ARQ-задачи для transactional email outbox.

`process_email_outbox` — основной диспетчер, запускается каждые несколько секунд:
   1. Атомарно захватывает PENDING-записи (FOR UPDATE SKIP LOCKED).
   2. Для каждой строит MIME и шлёт через aiosmtplib.
   3. По результату обновляет outbox-строку (SENT / PENDING+next_attempt_at / DLQ).

`cleanup_email_outbox` — раз в сутки чистит старые SENT записи.
"""

from __future__ import annotations

import base64
from email.mime.image import MIMEImage
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


def _sanitize_header(value: str) -> str:
    """Удаляет CR/LF из значения MIME-заголовка (защита от header injection, E3).

    Subject/To берутся из данных БД (`news_title`, `booking.title`), которые
    может контролировать пользователь. На политике ``compat32`` присвоение
    ``msg["Subject"] = value`` НЕ фильтрует переводы строк, поэтому
    ``"тема\\r\\nBcc: victim@x"`` инъектировала бы скрытого получателя или
    лишние заголовки. Схлопываем любые CR/LF в пробел.
    """
    if not value:
        return value
    return value.replace("\r", " ").replace("\n", " ")


def _build_mime(row: dict, cfg: dict) -> MIMEMultipart:
    kind = row["kind"]
    to_email = _sanitize_header(row["to_email"])
    subject = _sanitize_header(row["subject"])
    from_address = _sanitize_header(cfg["from_address"] or "portal@company.local")
    body_html = row["body_html"] or ""
    body_text = row["body_text"]
    payload = row["payload"] or {}

    if kind == KIND_MEETING:
        outer = MIMEMultipart("mixed")
        outer["Subject"] = subject
        outer["From"] = from_address
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

    alternative = MIMEMultipart("alternative")
    if body_text:
        alternative.attach(MIMEText(body_text, "plain", "utf-8"))
    alternative.attach(MIMEText(body_html, "html", "utf-8"))

    inline_images = payload.get("inline_images") or []
    if inline_images:
        related = MIMEMultipart("related")
        related["Subject"] = subject
        related["From"] = from_address
        related["To"] = to_email
        related.attach(alternative)
        for img in inline_images:
            _attach_inline_image(related, img)
        return related

    alternative["Subject"] = subject
    alternative["From"] = from_address
    alternative["To"] = to_email
    return alternative


def _attach_inline_image(container: MIMEMultipart, img: dict) -> None:
    """Attach one base64 inline image (referenced from HTML via ``cid:``)."""
    cid = str(img.get("cid") or "").strip()
    b64 = img.get("b64") or ""
    if not cid or not b64:
        return
    try:
        data = base64.b64decode(b64)
    except Exception:
        logger.warning("email_outbox.inline_image_decode_failed", cid=cid)
        return
    subtype = (img.get("mime") or "image/jpeg").split("/")[-1] or "jpeg"
    part = MIMEImage(data, _subtype=subtype)
    part.add_header("Content-ID", f"<{cid}>")
    part.add_header("Content-Disposition", "inline", filename=f"{cid}.{subtype}")
    container.attach(part)


__all__ = ["cleanup_email_outbox", "process_email_outbox"]
