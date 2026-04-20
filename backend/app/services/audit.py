"""Audit helper — fire-and-forget push to Redis queue."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

AUDIT_QUEUE_KEY = "audit_queue"


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
        await redis.rpush(AUDIT_QUEUE_KEY, json.dumps(record))
    except Exception as exc:
        logger.warning("audit.push_failed", error=str(exc), event_type=event_type)
