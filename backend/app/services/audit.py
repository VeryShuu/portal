"""Audit helper — fire-and-forget push to Redis queue."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

AUDIT_QUEUE_KEY = "audit_queue"
# Кумулятивный счётчик пушей по event_type — кросс-процессная замена локальному
# prometheus Counter (uvicorn --workers 2). Пишется HINCRBY здесь, читается
# воркер-снапшотом (worker/tasks/metrics.py) и гидрируется дельтами в API
# (middleware/metrics.py). Основа алерта PortalAuditPushRateZero.
AUDIT_METRICS_KEY = "audit:metrics:pushed"


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
        await redis.rpush(AUDIT_QUEUE_KEY, json.dumps(record))  # type: ignore[misc]  # redis-py async-overload typing
        # Кросс-процессный счётчик: прод крутит uvicorn --workers 2, локальный
        # prometheus Counter живёт в каждом процессе отдельно, а /metrics
        # попадает на случайный — серия «прыгала» между процессами. Кумулятив
        # копится в Redis-хэше; API-процессы гидрируют дельты в свои Counter
        # на каждом scrape (middleware/metrics.py::_hydrate_audit_push_counters)
        # — тот же паттерн, что у ARQ-метрик (worker/tasks/metrics.py).
        with contextlib.suppress(Exception):  # метрика не должна ломать push
            await redis.hincrby(AUDIT_METRICS_KEY, event_type, 1)  # type: ignore[misc]  # redis-py async-overload typing
    except Exception as exc:
        logger.exception(
            "audit.push_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            event_type=event_type,
        )


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
