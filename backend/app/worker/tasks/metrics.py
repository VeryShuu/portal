"""ARQ task that periodically refreshes custom Prometheus gauges.

These gauges live in the worker process — but the same metric names are
also exported by the API process where they are populated by request
handlers.  The values produced here are persisted to Redis so that the
API process can pull the latest snapshot when scraped by Prometheus.
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.audit import AUDIT_QUEUE_KEY

logger = get_logger(__name__)
settings = get_settings()

METRICS_SNAPSHOT_KEY = "metrics:snapshot"
WORKER_HEARTBEAT_KEY = "arq:heartbeat"
WORKER_HEARTBEAT_TTL = 90  # seconds — if not refreshed in 90 s, worker is considered dead
PHOTOS_ORIGINALS_DIR = Path("/data/photos/originals")

# Redis hashes for ARQ job accounting (cross-process: worker writes, API reads).
#   ARQ_JOBS_KEY     — {field "{function}:{status}": cumulative count}
#   ARQ_JOB_TIME_KEY — {field "{function}": [count, sum_ms]} — for histogram.
ARQ_JOBS_KEY = "arq:metrics:jobs"
ARQ_JOB_TIME_KEY = "arq:metrics:job_ms"


def track_arq_job(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap an ARQ task to record job counts and duration in Redis.

    The worker is a separate process from the API that serves ``/metrics``,
    so Prometheus counters cannot be incremented directly. Instead we write
    to Redis hashes (atomic ``HINCRBY``), and the API hydrates them into
    ``portal_arq_jobs_total`` / ``portal_arq_job_duration_seconds`` on each
    scrape (see ``middleware/metrics.py``).

    Records per job: one ``started`` count, one terminal count (``succeeded``
    or ``failed``), and duration in milliseconds. Exceptions are re-raised
    so ARQ's own retry/failure handling is unaffected.
    """

    @functools.wraps(func)
    async def wrapper(ctx: dict, *args: Any, **kwargs: Any) -> Any:
        name = func.__name__
        redis = ctx.get("redis")
        start = time.monotonic()
        if redis is not None:
            try:
                await redis.hincrby(ARQ_JOBS_KEY, f"{name}:started", 1)
            except Exception as exc:  # pragma: no cover - never break a job
                logger.warning("arq_metrics.record_failed", stage="start", error=str(exc))
        status = "succeeded"
        try:
            return await func(ctx, *args, **kwargs)
        except Exception:
            status = "failed"
            raise
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if redis is not None:
                try:
                    pipe = redis.pipeline()
                    pipe.hincrby(ARQ_JOBS_KEY, f"{name}:{status}", 1)
                    pipe.hincrby(ARQ_JOB_TIME_KEY, f"{name}:count", 1)
                    pipe.hincrby(ARQ_JOB_TIME_KEY, f"{name}:sum", elapsed_ms)
                    await pipe.execute()
                except Exception as exc:  # pragma: no cover - never break a job
                    logger.warning("arq_metrics.record_failed", stage="end", error=str(exc))

    return wrapper


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

    # 5. ARQ job accounting — HGETALL the worker-written hashes. Keys carry the
    # cumulative counts; the API hydrates deltas into Prometheus counters.
    try:
        jobs_raw = await redis.hgetall(ARQ_JOBS_KEY)
        time_raw = await redis.hgetall(ARQ_JOB_TIME_KEY)
        snapshot["arq_jobs"] = {
            k.decode() if isinstance(k, bytes) else k: int(v)
            for k, v in jobs_raw.items()
        }
        snapshot["arq_job_ms"] = {
            k.decode() if isinstance(k, bytes) else k: int(v)
            for k, v in time_raw.items()
        }
    except Exception as exc:
        logger.warning("metrics.arq_jobs_failed", error=str(exc))

    # Persist the snapshot for the API process to consume
    try:
        await redis.set(METRICS_SNAPSHOT_KEY, json.dumps(snapshot, default=str), ex=300)
    except Exception as exc:
        logger.warning("metrics.snapshot_publish_failed", error=str(exc))

    logger.info("metrics.refreshed", keys=list(snapshot.keys()))
    return snapshot


async def worker_heartbeat(ctx: dict) -> None:
    """Write a TTL-bound key to Redis so healthchecks can verify the ARQ loop is alive.

    Runs every 30 seconds via cron.  The key ``arq:heartbeat`` expires after
    ``WORKER_HEARTBEAT_TTL`` seconds (90 s).  The Docker healthcheck reads this
    key; absence means the worker process is stuck or dead.
    """
    redis = ctx["redis"]
    await redis.set(WORKER_HEARTBEAT_KEY, "1", ex=WORKER_HEARTBEAT_TTL)
