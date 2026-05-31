"""Transactional outbox для исходящих email.

Все email-уведомления записываются в таблицу email_outbox в той же транзакции,
что и бизнес-операция. Отдельный воркер (cron `process_email_outbox`) забирает
PENDING-записи и шлёт через SMTP. Это устраняет потерю писем при падении Redis
и даёт админу полный контроль (см. EmailOutboxTab в админке).
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.worker.tasks.email_utils import OUTBOX_MAX_ATTEMPTS, compute_retry_defer

logger = get_logger(__name__)

KIND_MEETING = "meeting"
KIND_NEWS = "news"
KIND_KB_SUGGESTION = "kb_suggestion"
KIND_FILE_SHARE = "file_share"
KIND_GENERIC = "generic"

STATUS_PENDING = "PENDING"
STATUS_SENDING = "SENDING"
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"
STATUS_DLQ = "DLQ"
STATUS_CANCELLED = "CANCELLED"


async def enqueue_outbox_email(
    session: AsyncSession,
    *,
    kind: str,
    to_email: str,
    subject: str,
    body_html: str = "",
    body_text: str | None = None,
    payload: dict[str, Any] | None = None,
    related_resource_type: str | None = None,
    related_resource_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
    max_attempts: int = OUTBOX_MAX_ATTEMPTS,
) -> uuid.UUID:
    """Создаёт PENDING-запись в email_outbox.

    Caller отвечает за commit транзакции (outbox-паттерн: запись должна
    коммититься атомарно с бизнес-операцией).
    """
    row = await session.execute(
        text(
            """
            INSERT INTO email_outbox (
                kind, to_email, subject, body_html, body_text, payload,
                related_resource_type, related_resource_id, created_by_user_id,
                max_attempts
            )
            VALUES (
                :kind, :to_email, :subject, :body_html, :body_text,
                CAST(:payload AS JSONB),
                :rtype, :rid, :uid, :max_attempts
            )
            RETURNING id
            """
        ),
        {
            "kind": kind,
            "to_email": to_email,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "payload": _json_dumps(payload or {}),
            "rtype": related_resource_type,
            "rid": related_resource_id,
            "uid": created_by_user_id,
            "max_attempts": max_attempts,
        },
    )
    new_id: uuid.UUID = row.scalar_one()
    logger.info(
        "email_outbox.enqueued",
        outbox_id=str(new_id),
        kind=kind,
        to=to_email,
    )
    return new_id


async def claim_pending(session: AsyncSession, *, limit: int = 20) -> list[dict]:
    """Захватывает до `limit` PENDING-записей в SENDING (атомарно через SKIP LOCKED)."""
    rows = (
        (
            await session.execute(
                text(
                    """
                WITH cte AS (
                    SELECT id
                    FROM email_outbox
                    WHERE status = 'PENDING'
                      AND next_attempt_at <= NOW()
                    ORDER BY next_attempt_at
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE email_outbox e
                SET status = 'SENDING', updated_at = NOW()
                FROM cte
                WHERE e.id = cte.id
                RETURNING e.id, e.kind, e.to_email, e.subject, e.body_html,
                          e.body_text, e.payload, e.attempts, e.max_attempts
                """
                ),
                {"limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def mark_sent(session: AsyncSession, outbox_id: uuid.UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status='SENT', sent_at=NOW(), updated_at=NOW(),
                attempts = attempts + 1,
                last_error = NULL, last_error_type = NULL, last_error_class = NULL
            WHERE id = :id
            """
        ),
        {"id": outbox_id},
    )


async def mark_failed(
    session: AsyncSession,
    outbox_id: uuid.UUID,
    *,
    error: str,
    error_type: str,
    error_class: str,
    current_attempts: int,
    max_attempts: int,
) -> str:
    """После неуспешной попытки: либо ставит next_attempt_at и status=PENDING,
    либо помечает DLQ (permanent / превышение max_attempts).

    Возвращает новый статус ('PENDING' | 'DLQ').
    """
    new_attempts = current_attempts + 1
    is_permanent = error_class == "permanent"
    is_exhausted = new_attempts >= max_attempts
    final = is_permanent or is_exhausted

    if final:
        new_status = STATUS_DLQ
        next_at_clause = "next_attempt_at = next_attempt_at"
        defer = 0
    else:
        new_status = STATUS_PENDING
        defer = compute_retry_defer(new_attempts, error_class)  # type: ignore[arg-type]
        next_at_clause = "next_attempt_at = NOW() + make_interval(secs => :defer)"

    params = {
        "id": outbox_id,
        "status": new_status,
        "attempts": new_attempts,
        "error": (error or "")[:4000],
        "error_type": (error_type or "")[:128],
        "error_class": (error_class or "")[:16],
    }
    if not final:
        params["defer"] = defer

    await session.execute(
        text(
            f"""
            UPDATE email_outbox
            SET status = :status,
                attempts = :attempts,
                last_error = :error,
                last_error_type = :error_type,
                last_error_class = :error_class,
                updated_at = NOW(),
                {next_at_clause}
            WHERE id = :id
            """
        ),
        params,
    )
    return new_status


async def reschedule_for_retry(
    session: AsyncSession,
    outbox_id: uuid.UUID,
    *,
    reset_attempts: bool = False,
) -> bool:
    """Ручной resend: переводит запись в PENDING с next_attempt_at = NOW().

    Работает для статусов FAILED, DLQ, CANCELLED, SENT.
    Возвращает True, если запись обновлена.
    """
    result = await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status = 'PENDING',
                next_attempt_at = NOW(),
                attempts = CASE WHEN :reset THEN 0 ELSE attempts END,
                updated_at = NOW()
            WHERE id = :id
              AND status IN ('FAILED','DLQ','CANCELLED','SENT','PENDING')
            """
        ),
        {"id": outbox_id, "reset": reset_attempts},
    )
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


async def cancel(session: AsyncSession, outbox_id: uuid.UUID) -> bool:
    """Отменить отправку (только из PENDING/DLQ/FAILED)."""
    result = await session.execute(
        text(
            """
            UPDATE email_outbox
            SET status = 'CANCELLED', updated_at = NOW()
            WHERE id = :id
              AND status IN ('PENDING','DLQ','FAILED')
            """
        ),
        {"id": outbox_id},
    )
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


async def cleanup_old_sent(session: AsyncSession, *, older_than_days: int = 30) -> int:
    """Чистит старые SENT записи. Должно вызываться из cron."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await session.execute(
        text("DELETE FROM email_outbox WHERE status='SENT' AND sent_at < :cutoff"),
        {"cutoff": cutoff},
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def encode_ical_bytes(ical_bytes: bytes) -> str:
    return base64.b64encode(ical_bytes).decode("ascii")


def decode_ical_bytes(encoded: str) -> bytes:
    return base64.b64decode(encoded.encode("ascii"))


def _json_dumps(value: dict[str, Any]) -> str:
    import json as _json

    return _json.dumps(value, ensure_ascii=False, default=str)
