"""
ARQ-задачи для audit_log:
  - flush_audit_queue: batch INSERT из Redis list → PostgreSQL
  - create_next_audit_partition: создать партицию на следующий месяц
  - drop_old_audit_partitions: удалить партиции старше 12 месяцев
"""

import json
from datetime import UTC, datetime

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.audit import AUDIT_QUEUE_KEY

logger = get_logger(__name__)
settings = get_settings()

PROCESSING_KEY = "audit_processing"
BATCH_SIZE = 500
FLUSH_LOCK_KEY = "audit:flush:lock"
FLUSH_LOCK_TTL = 30


def _parse_dt(value: str | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


async def flush_audit_queue(ctx: dict) -> int:
    redis = ctx["redis"]
    pool = ctx["pg_pool"]
    inserted = 0

    acquired = await redis.set(FLUSH_LOCK_KEY, "1", nx=True, ex=FLUSH_LOCK_TTL)
    if not acquired:
        logger.debug("audit.flush.skipped", reason="locked_by_another_worker")
        return 0

    try:
        while True:
            items = await redis.lrange(PROCESSING_KEY, 0, -1)
            if not items:
                for _ in range(BATCH_SIZE):
                    item = await redis.lmove(AUDIT_QUEUE_KEY, PROCESSING_KEY, "LEFT", "RIGHT")
                    if item is None:
                        break
                items = await redis.lrange(PROCESSING_KEY, 0, -1)

            if not items:
                break

            records = [json.loads(item) for item in items]
            if not records:
                await redis.delete(PROCESSING_KEY)
                break

            async with pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO audit_log
                        (event_type, user_id, user_email, resource_type, resource_id,
                         resource_title, ip_address, user_agent, metadata, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    [
                        (
                            r.get("event_type"),
                            r.get("user_id"),
                            r.get("user_email"),
                            r.get("resource_type"),
                            r.get("resource_id"),
                            r.get("resource_title"),
                            r.get("ip_address"),
                            r.get("user_agent"),
                            json.dumps(r.get("metadata", {})),
                            _parse_dt(r.get("created_at")),
                        )
                        for r in records
                    ],
                )
            inserted += len(records)
            await redis.delete(PROCESSING_KEY)
    except Exception as exc:
        logger.exception("audit.flush_failed", error=str(exc), error_type=type(exc).__name__)
        raise
    finally:
        await redis.delete(FLUSH_LOCK_KEY)

    if inserted:
        logger.info("audit.flushed", count=inserted)
    return inserted


async def create_next_audit_partition(ctx: dict) -> str:
    from app.services.audit_partitions import ensure_partitions

    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url, statement_cache_size=0)
    try:
        created = await ensure_partitions(conn, months_ahead=3)
        logger.info("audit.partitions_created", tables=created)
        return str(created)
    finally:
        await conn.close()


async def drop_old_audit_partitions(ctx: dict) -> str:
    from app.services.audit_partitions import drop_old_partitions

    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url, statement_cache_size=0)
    try:
        dropped = await drop_old_partitions(conn, retention_months=12)
        logger.info("audit.partitions_dropped", tables=dropped)
        return str(dropped)
    finally:
        await conn.close()


async def cleanup_idempotency_keys(ctx: dict) -> str:
    """Delete idempotency_keys older than 24 hours.

    Idempotency keys are only needed for the dedup window (typically minutes).
    Without a cleanup job they accumulate indefinitely.
    """
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url, statement_cache_size=0)
    try:
        result = await conn.execute(
            "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours'"
        )
        deleted = int(result.split()[-1]) if result else 0
        logger.info("idempotency_keys.cleaned", deleted=deleted)
        return str(deleted)
    finally:
        await conn.close()
