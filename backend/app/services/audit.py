"""Audit helper — fire-and-forget push to Redis queue."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)

AUDIT_QUEUE_KEY = "audit_queue"


async def log(
    *,
    db: AsyncSession | None = None,  # kept for API compatibility, no longer used
    user_id: str | None = None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Direct insert into audit_log using an isolated session (fire-and-forget, does not raise).

    Uses a fresh session so this can never accidentally commit the caller's
    in-progress transaction, regardless of call order.
    """
    try:
        async with AsyncSessionLocal() as audit_db:
            await audit_db.execute(
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
            await audit_db.commit()
    except Exception as exc:
        logger.warning(
            "audit.log_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            event_type=event_type,
        )
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)
        except Exception:  # pragma: no cover
            pass


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
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)
        except Exception:  # pragma: no cover
            pass


AuditEmitter = Callable[..., Awaitable[None]]


def make_audit_emitter(resource_type: str) -> AuditEmitter:
    """Build an audit emitter with ``resource_type`` bound.

    Thin wrapper over :func:`push_audit_event` that removes the repeated
    ``resource_type=...`` boilerplate at call sites in a module. The emitter is
    a transparent passthrough: it injects the bound ``resource_type`` and
    forwards every other keyword unchanged, so the resulting
    ``push_audit_event`` call is identical to a hand-written one (same kwargs,
    no spurious defaults). It resolves ``push_audit_event`` from this module's
    namespace at call time, so tests may patch
    ``app.services.audit.push_audit_event`` to intercept.
    """

    async def emit(redis: Redis, **kwargs: Any) -> None:
        await push_audit_event(redis, resource_type=resource_type, **kwargs)

    return emit
