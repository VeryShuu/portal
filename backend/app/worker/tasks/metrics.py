"""ARQ task that periodically refreshes custom Prometheus gauges.

These gauges live in the worker process — but the same metric names are
also exported by the API process where they are populated by request
handlers.  The values produced here are persisted to Redis so that the
API process can pull the latest snapshot when scraped by Prometheus.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.audit import AUDIT_QUEUE_KEY

logger = get_logger(__name__)
settings = get_settings()

METRICS_SNAPSHOT_KEY = "metrics:snapshot"
PHOTOS_ORIGINALS_DIR = Path("/data/photos/originals")


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


async def refresh_custom_metrics(ctx: dict) -> dict:
    """Refresh custom gauges and store the snapshot in Redis."""
    redis = ctx["redis"]
    pool = ctx.get("pg_pool")

    snapshot: dict[str, float | int | dict | str] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

    # 1. Audit queue depth
    try:
        snapshot["audit_queue_depth"] = int(await redis.llen(AUDIT_QUEUE_KEY))
        snapshot["audit_processing_depth"] = int(await redis.llen("audit_processing"))
    except Exception as exc:
        logger.warning("metrics.audit_queue_failed", error=str(exc))

    # 2. SSE connections — read from the global tracking key (single ZCARD)
    try:
        snapshot["sse_connections"] = int(await redis.zcard("sse:global"))
    except Exception as exc:
        logger.warning("metrics.sse_scan_failed", error=str(exc))

    # 3. DB-derived gauges (only if DB available)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        (SELECT count(*) FROM users WHERE auth_source='keycloak') AS u_kc,
                        (SELECT count(*) FROM users WHERE auth_source='local')    AS u_local,
                        (SELECT count(*) FROM kb_articles
                          WHERE status='published' AND deleted_at IS NULL)        AS kb_pub,
                        (SELECT count(*) FROM kb_articles
                          WHERE status='draft' AND deleted_at IS NULL)            AS kb_draft,
                        (SELECT count(*) FROM news
                          WHERE status='published' AND deleted_at IS NULL)        AS news_pub,
                        (SELECT count(*) FROM news
                          WHERE status='draft' AND deleted_at IS NULL)            AS news_draft,
                        (SELECT count(DISTINCT user_id) FROM audit_log
                          WHERE created_at >= $1 AND user_id IS NOT NULL)         AS active_1h
                    """,
                    datetime.now(tz=UTC) - timedelta(hours=1),
                )
                if row is not None:
                    snapshot["users_total"] = {
                        "keycloak": int(row["u_kc"] or 0),
                        "local": int(row["u_local"] or 0),
                    }
                    snapshot["kb_articles_total"] = {
                        "published": int(row["kb_pub"] or 0),
                        "draft": int(row["kb_draft"] or 0),
                    }
                    snapshot["news_published_total"] = {
                        "published": int(row["news_pub"] or 0),
                        "draft": int(row["news_draft"] or 0),
                    }
                    snapshot["active_users_1h"] = int(row["active_1h"] or 0)
        except Exception as exc:
            logger.warning("metrics.db_failed", error=str(exc))

    # 4. Photo storage size — offloaded to thread pool to avoid blocking the event loop
    try:
        loop = asyncio.get_running_loop()
        snapshot["photo_storage_bytes"] = await loop.run_in_executor(
            None, _dir_size_bytes, PHOTOS_ORIGINALS_DIR
        )
    except Exception as exc:
        logger.warning("metrics.photo_size_failed", error=str(exc))

    # Persist the snapshot for the API process to consume
    try:
        await redis.set(METRICS_SNAPSHOT_KEY, json.dumps(snapshot, default=str), ex=300)
    except Exception as exc:
        logger.warning("metrics.snapshot_publish_failed", error=str(exc))

    logger.info("metrics.refreshed", keys=list(snapshot.keys()))
    return snapshot
