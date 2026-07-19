"""Transactional outbox для исходящих сообщений в мессенджеры.

Полный аналог :mod:`app.services.email_outbox` для не-email каналов (MAX,
потом — Telegram/Slack). Запись в ``messenger_outbox`` ставится в **той же
транзакции**, что и бизнес-операция (новая заявка), — outbox-инвариант
(см. AGENTS.md). Отдельный воркер ``process_messenger_outbox`` (cron каждые
15с) забирает PENDING через ``FOR UPDATE SKIP LOCKED`` и шлёт через
провайдер-клиент.

Статусы/переходы идентичны email_outbox:
``PENDING → SENDING → SENT`` (успех) / ``→ PENDING+next_attempt_at`` (transient)
/ ``→ DLQ`` (permanent или превышение max_attempts).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.worker.tasks.email_utils import OUTBOX_MAX_ATTEMPTS, compute_retry_defer

logger = get_logger(__name__)

PROVIDER_MAX = "max"

STATUS_PENDING = "PENDING"
STATUS_SENDING = "SENDING"
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"
STATUS_DLQ = "DLQ"
STATUS_CANCELLED = "CANCELLED"


async def enqueue_messenger_message(
    session: AsyncSession,
    *,
    provider: str,
    chat_id: str,
    text: str,
    payload: dict[str, Any] | None = None,
    related_resource_type: str | None = None,
    related_resource_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
    max_attempts: int = OUTBOX_MAX_ATTEMPTS,
) -> uuid.UUID:
    """Создать PENDING-запись в messenger_outbox.

    Caller отвечает за commit (outbox-инвариант: запись коммитится атомарно с
    бизнес-операцией). ``payload`` хранит провайдер-специфичный контент — для
    MAX: ``{"attachments": [...], "format": "markdown"}`` (inline-keyboard и
    другие MEDIA-attachments).
    """
    from sqlalchemy import text as sql_text

    row = await session.execute(
        sql_text(
            """
            INSERT INTO messenger_outbox (
                provider, chat_id, text, payload,
                related_resource_type, related_resource_id, created_by_user_id,
                max_attempts
            )
            VALUES (
                :provider, :chat_id, :text, CAST(:payload AS JSONB),
                :rtype, :rid, :uid, :max_attempts
            )
            RETURNING id
            """
        ),
        {
            "provider": provider,
            "chat_id": chat_id,
            "text": text,
            "payload": _json_dumps(payload or {}),
            "rtype": related_resource_type,
            "rid": related_resource_id,
            "uid": created_by_user_id,
            "max_attempts": max_attempts,
        },
    )
    new_id: uuid.UUID = row.scalar_one()
    logger.info(
        "messenger_outbox.enqueued",
        outbox_id=str(new_id),
        provider=provider,
        chat_id=chat_id,
    )
    return new_id


async def claim_pending(session: AsyncSession, *, limit: int = 20) -> list[dict]:
    """Захватывает до ``limit`` PENDING-записей в SENDING атомарно (SKIP LOCKED).

    Возвращает список dict с полным набором полей, нужных воркеру для отправки
    и для последующего mark_sent/mark_failed.
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                WITH cte AS (
                    SELECT id
                    FROM messenger_outbox
                    WHERE status = 'PENDING'
                      AND next_attempt_at <= NOW()
                    ORDER BY next_attempt_at
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE messenger_outbox m
                SET status = 'SENDING', updated_at = NOW()
                FROM cte
                WHERE m.id = cte.id
                RETURNING m.id, m.provider, m.chat_id, m.text, m.payload,
                          m.attempts, m.max_attempts
                """
                ),
                {"limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def requeue_stale_sending(session: AsyncSession, *, older_than_seconds: int = 600) -> int:
    """Watchdog: вернуть «зависшие» SENDING-записи в PENDING.

    Аналог ``email_outbox.requeue_stale_sending``: если воркер упал между
    ``claim_pending`` и ``mark_sent``/``mark_failed``, строка остаётся в
    SENDING навсегда. Возвращаем в очередь, **не** инкрементируя attempts
    (попытка не была завершена).
    """
    result = await session.execute(
        text(
            """
            UPDATE messenger_outbox
            SET status = 'PENDING',
                next_attempt_at = NOW(),
                updated_at = NOW()
            WHERE status = 'SENDING'
              AND updated_at < NOW() - make_interval(secs => :older_than)
            """
        ),
        {"older_than": older_than_seconds},
    )
    count = result.rowcount or 0  # type: ignore[attr-defined]
    if count:
        logger.warning("messenger_outbox.requeued_stale_sending", count=count)
    return count


async def mark_sent(session: AsyncSession, outbox_id: uuid.UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE messenger_outbox
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
    """После неуспешной попытки: либо next_attempt_at + PENDING, либо DLQ.

    Возвращает новый статус ('PENDING' | 'DLQ'). Логика идентична email_outbox.
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

    sql = f"""
        UPDATE messenger_outbox
        SET status = :status,
            attempts = :attempts,
            last_error = :error,
            last_error_type = :error_type,
            last_error_class = :error_class,
            updated_at = NOW(),
            {next_at_clause}
        WHERE id = :id
        """  # nosec B608 — next_at_clause статический; данные в params.
    await session.execute(text(sql), params)
    return new_status


async def reschedule_for_retry(
    session: AsyncSession,
    outbox_id: uuid.UUID,
    *,
    reset_attempts: bool = False,
) -> bool:
    """Ручной resend: переводит запись в PENDING с next_attempt_at = NOW().

    Работает для статусов FAILED, DLQ, CANCELLED, SENT, PENDING.
    """
    result = await session.execute(
        text(
            """
            UPDATE messenger_outbox
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
            UPDATE messenger_outbox
            SET status = 'CANCELLED', updated_at = NOW()
            WHERE id = :id
              AND status IN ('PENDING','DLQ','FAILED')
            """
        ),
        {"id": outbox_id},
    )
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


async def cleanup_old_sent(session: AsyncSession, *, older_than_days: int = 30) -> int:
    """Чистит старые SENT записи. Вызывается из cron."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await session.execute(
        text("DELETE FROM messenger_outbox WHERE status='SENT' AND sent_at < :cutoff"),
        {"cutoff": cutoff},
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _json_dumps(value: dict[str, Any]) -> str:
    import json as _json

    return _json.dumps(value, ensure_ascii=False, default=str)
