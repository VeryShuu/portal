"""Audit helper — fire-and-forget push to Redis queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

AUDIT_QUEUE_KEY = "audit_queue"


async def log(
    *,
    db: AsyncSession,
    user_id: str | None = None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Direct insert into audit_log (fire-and-forget, does not raise)."""
    try:
        await db.execute(
            text(
                "INSERT INTO audit_log (event_type, user_id, metadata, created_at) "
                "VALUES (:event_type, :user_id, CAST(:metadata AS jsonb), :created_at)"
            ),
            {
                "event_type": event_type,
                "user_id": user_id,
                "metadata": json.dumps(metadata or {}),
                "created_at": datetime.now(UTC),
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning(
            "audit.log_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            event_type=event_type,
        )


async def push_audit_event(
    redis: Redis,
    *,
    event_type: str,
    user_id: str | None = None,
    user_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    resource_title: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        record = {
            "event_type": event_type,
            "user_id": user_id,
            "user_email": user_email,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_title": resource_title,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        await redis.rpush(AUDIT_QUEUE_KEY, json.dumps(record))  # type: ignore[misc]
        try:
            from app.core.metrics import audit_events_pushed

            audit_events_pushed.labels(event_type=event_type).inc()
        except Exception:  # pragma: no cover
            pass
    except Exception as exc:
        logger.exception(
            "audit.push_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            event_type=event_type,
        )
