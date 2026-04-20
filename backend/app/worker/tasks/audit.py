"""
ARQ-задачи для audit_log:
  - flush_audit_queue: batch INSERT из Redis list → PostgreSQL
  - create_next_audit_partition: создать партицию на следующий месяц
  - drop_old_audit_partitions: удалить партиции старше 12 месяцев
"""

import json
from datetime import datetime, timezone

import asyncpg
from dateutil.relativedelta import relativedelta

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

AUDIT_QUEUE_KEY = "audit_queue"
BATCH_SIZE = 500


async def flush_audit_queue(ctx: dict) -> int:
    redis = ctx["redis"]
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    inserted = 0

    try:
        while True:
            pipeline = await redis.lmpop(1, AUDIT_QUEUE_KEY, direction="LEFT", count=BATCH_SIZE)
            if not pipeline:
                break

            records = [json.loads(item) for item in pipeline[1]]
            if not records:
                break

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
                        r.get("created_at", datetime.now(tz=timezone.utc).isoformat()),
                    )
                    for r in records
                ],
            )
            inserted += len(records)
    except Exception as exc:
        logger.error("audit.flush_failed", error=str(exc))
    finally:
        await conn.close()

    if inserted:
        logger.info("audit.flushed", count=inserted)
    return inserted


async def create_next_audit_partition(ctx: dict) -> str:
    from app.services.audit_partitions import ensure_partitions
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    try:
        created = await ensure_partitions(conn, months_ahead=2)
        logger.info("audit.partitions_created", tables=created)
        return str(created)
    finally:
        await conn.close()


async def drop_old_audit_partitions(ctx: dict) -> str:
    from app.services.audit_partitions import drop_old_partitions
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)
    try:
        dropped = await drop_old_partitions(conn, retention_months=12)
        logger.info("audit.partitions_dropped", tables=dropped)
        return str(dropped)
    finally:
        await conn.close()
