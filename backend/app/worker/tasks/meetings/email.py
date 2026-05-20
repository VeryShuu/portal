"""ARQ-задачи для email уведомлений о встречах."""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Literal

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


async def send_meeting_email(
    ctx: dict,
    *,
    to_email: str,
    subject: str,
    html_body: str,
    ical_bytes: bytes,
    method: Literal["REQUEST", "CANCEL"],
) -> None:
    try:
        from app.core.modules_config import load_modules

        modules = load_modules()
        if not getattr(modules.meetings, "enabled", True):
            logger.info("meetings.email.skipped_module_disabled", to=to_email)
            return
    except Exception as exc:
        logger.warning("meetings.email.module_check_failed", error=str(exc))

    cfg = load_smtp_config()

    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"] = cfg["from_address"] or "portal@company.local"
    outer["To"] = to_email
    outer["Content-Class"] = "urn:content-classes:calendarmessage"

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(html_body, "html", "utf-8"))

    ical_inline = MIMEText(ical_bytes.decode("utf-8"), "calendar", "utf-8")
    ical_inline.set_param("method", method)
    ical_inline.set_param("charset", "UTF-8")
    alternative.attach(ical_inline)

    outer.attach(alternative)

    job_try = int(ctx.get("job_try") or 1)

    try:
        await smtp_send(outer, cfg)
        logger.info("meetings.email.sent", to=to_email, subject=subject, method=method)

        from app.services.meetings.audit import EMAIL_SENT, push_meetings_audit

        await push_meetings_audit(
            action=EMAIL_SENT,
            user=None,
            request=None,
            details={"to": to_email, "method": method},
        )
        return

    except Exception as exc:
        error_class = classify_smtp_error(exc)
        error_type = type(exc).__name__
        logger.exception(
            "meetings.email.send_failed",
            error=str(exc),
            error_type=error_type,
            error_class=error_class,
            job_try=job_try,
            to=to_email,
        )

        is_final = error_class == "permanent" or job_try >= MAX_TRIES

        try:
            from app.services.meetings.audit import EMAIL_FAILED, push_meetings_audit

            await push_meetings_audit(
                action=EMAIL_FAILED,
                user=None,
                request=None,
                details={
                    "to": to_email,
                    "method": method,
                    "error": str(exc),
                    "error_type": error_type,
                    "error_class": error_class,
                    "job_try": job_try,
                    "final": is_final,
                },
            )
        except Exception as audit_exc:
            logger.warning("meetings.email.audit_write_failed", error=str(audit_exc))

        if is_final:
            raise

        defer = compute_retry_defer(job_try, error_class)
        raise Retry(defer=defer) from exc


send_meeting_email.max_tries = MAX_TRIES  # type: ignore[attr-defined]
send_meeting_email.job_timeout = JOB_TIMEOUT_SECONDS  # type: ignore[attr-defined]
