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
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.constants import HELPDESK_ARCHIVE_AFTER_DAYS
from app.core.logging import get_logger
from app.services.audit import AUDIT_METRICS_KEY, AUDIT_QUEUE_KEY

logger = get_logger(__name__)
settings = get_settings()

METRICS_SNAPSHOT_KEY = "metrics:snapshot"
WORKER_HEARTBEAT_KEY = "arq:heartbeat"
# Persistent (no TTL) key: photo-storage size, written daily by
# ``refresh_photo_storage`` cron. ``refresh_custom_metrics`` only READS it —
# rglob по всем оригиналам каждые 30 секунд создавали постоянную дисковую
# нагрузку на большом хранилище (а storage-collector и так делает du той же
# папки каждые 5 минут). Ключ бессрочный: gauge сохраняет последнее значение
# до следующего суточного пересчёта.
PHOTO_STORAGE_KEY = "metrics:photo_storage"
# Separate timestamp key for age-based alerting. WORKER_HEARTBEAT_KEY is a pure
# TTL key (value "1", TTL 90s) consumed by the Docker healthcheck; it carries no
# timestamp, so a consumer cannot compute "how long ago the worker last ticked".
# This companion key stores the wall-clock unix time of each tick and is read by
# refresh_custom_metrics into ``portal_worker_last_heartbeat_seconds``. Absent
# key (worker never started / dead long enough for TTL) → the gauge is not
# hydrated → the PortalWorkerDown alert (time() - gauge > N) fires.
WORKER_HEARTBEAT_MTIME_KEY = "arq:heartbeat:mtime"
WORKER_HEARTBEAT_TTL = 90  # seconds — if not refreshed in 90 s, worker is considered dead
PHOTOS_ORIGINALS_DIR = Path("/data/photos/originals")

# ARQ stores its pending-queue as a Redis ZSET under this key (arq's
# ``default_queue_name``; WorkerSettings does not override queue_name). Read via
# ZCARD in refresh_custom_metrics → portal_arq_queue_depth gauge.
ARQ_QUEUE_KEY = "arq:queue"

# Redis hashes for ARQ job accounting (cross-process: worker writes, API reads).
#   ARQ_JOBS_KEY     — {field "{function}:{status}": cumulative count}
#   ARQ_JOB_TIME_KEY — {field "{function}": [count, sum_ms]} — for histogram.
ARQ_JOBS_KEY = "arq:metrics:jobs"
ARQ_JOB_TIME_KEY = "arq:metrics:job_ms"


def _arq_result_status(result: Any) -> str:
    """Classify explicit unsuccessful task results without changing ARQ semantics.

    Several worker tasks intentionally return a structured error instead of
    raising, so callers can inspect the safe reason. ARQ treats that as a
    successful execution and must keep doing so; monitoring records the business
    outcome separately as ``result_failed``. Empty errors, skipped results and
    non-mapping values remain successful.
    """
    if not isinstance(result, Mapping):
        return "succeeded"
    if result.get("ok") is False:
        return "result_failed"
    if result.get("error"):
        return "result_failed"
    return "succeeded"


def track_arq_job(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap an ARQ task to record job counts and duration in Redis.

    The worker is a separate process from the API that serves ``/metrics``,
    so Prometheus counters cannot be incremented directly. Instead we write
    to Redis hashes (atomic ``HINCRBY``), and the API hydrates them into
    ``portal_arq_jobs_total`` / ``portal_arq_job_duration_seconds`` on each
    scrape (see ``middleware/metrics.py``).

    Counts attempts: one started and one observed outcome (succeeded,
    result_failed, failed, timeout or cancelled), plus duration. A mapping with
    ``ok is False`` or a non-empty ``error`` is recorded as ``result_failed``
    but returned unchanged. Exceptions/cancellation propagate unchanged so ARQ
    retains control over retries and shutdown.

    ARQ's external wait_for deadline sends CancelledError to this coroutine;
    only ARQ observes the resulting TimeoutError. A deadline and shutdown
    cannot be distinguished here. cancelled therefore means observed
    interruption, including deadlines; timeout means TimeoutError raised
    inside the task. No result retention or retry policy is changed.
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
            result = await func(ctx, *args, **kwargs)
            status = _arq_result_status(result)
            return result
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except TimeoutError:
            status = "timeout"
            raise
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


async def _collect_audit_depths(redis: Any, snapshot: dict) -> None:
    """Audit queue + processing-list depths (LLLEN)."""
    try:
        snapshot["audit_queue_depth"] = int(await redis.llen(AUDIT_QUEUE_KEY))
        snapshot["audit_processing_depth"] = int(await redis.llen("audit_processing"))
    except Exception as exc:
        logger.warning("metrics.audit_queue_failed", error=str(exc))


async def _collect_audit_push_accounting(redis: Any, snapshot: dict) -> None:
    """Audit push accounting — HGETALL the API-written hash (cumulative per
    event_type). The API hydrates deltas into portal_audit_events_pushed_total
    on each scrape (middleware/metrics.py) — cross-process counter pattern."""
    try:
        raw = await redis.hgetall(AUDIT_METRICS_KEY)
        snapshot["audit_pushed"] = {
            k.decode() if isinstance(k, bytes) else k: int(v) for k, v in raw.items()
        }
    except Exception as exc:
        logger.warning("metrics.audit_push_failed", error=str(exc))


async def _collect_worker_heartbeat(redis: Any, snapshot: dict) -> None:
    """Worker heartbeat mtime — basis for PortalWorkerDown alerting.

    Absent key (worker never started / TTL expired because it died) → the
    field is omitted and the gauge is not hydrated this cycle, so the gauge
    retains the last known value and its age keeps growing.
    """
    try:
        mtime = await redis.get(WORKER_HEARTBEAT_MTIME_KEY)
        if mtime is not None:
            snapshot["worker_heartbeat_ts"] = int(mtime)
    except Exception as exc:
        logger.warning("metrics.worker_heartbeat_failed", error=str(exc))


async def _collect_arq_queue_depth(redis: Any, snapshot: dict) -> None:
    """ARQ pending-queue depth (ZCARD). Growing depth = worker not keeping up
    (slow/dead jobs) while enqueue continues. Basis for PortalArqQueueBacklog."""
    try:
        snapshot["arq_queue_depth"] = int(await redis.zcard(ARQ_QUEUE_KEY))
    except Exception as exc:
        logger.warning("metrics.arq_queue_failed", error=str(exc))


async def _collect_sse_connections(redis: Any, snapshot: dict) -> None:
    """SSE connections — read from the global tracking key (single ZCARD)."""
    try:
        snapshot["sse_connections"] = int(await redis.zcard("sse:global"))
    except Exception as exc:
        logger.warning("metrics.sse_scan_failed", error=str(exc))


async def _collect_db_gauges(pool: Any, snapshot: dict) -> None:
    """DB-derived gauges (users/kb/news/helpdesk/outbox). Only if DB available."""
    if pool is None:
        return
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
                      WHERE created_at >= $1 AND user_id IS NOT NULL)         AS active_1h,
                    (SELECT count(*) FROM helpdesk_tickets
                      WHERE status='closed'
                        AND closed_at < NOW() - ($2 * INTERVAL '1 day'))      AS hd_archive_backlog
                """,
                datetime.now(tz=UTC) - timedelta(hours=1),
                HELPDESK_ARCHIVE_AFTER_DAYS,
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
                snapshot["helpdesk_archive_backlog"] = int(row["hd_archive_backlog"] or 0)

            # Outbox health — visibility into email/MAX delivery pipeline.
            # Без этого копящиеся/DLQ-ящиеся письма невидимы до жалоб юзеров.
            outbox = await conn.fetchrow(
                """
                SELECT
                    (SELECT count(*) FROM email_outbox
                      WHERE status = 'PENDING')                      AS e_pending,
                    (SELECT count(*) FROM email_outbox
                      WHERE status = 'DLQ')                           AS e_dlq,
                    (SELECT count(*) FROM email_outbox
                      WHERE status = 'SENDING'
                        AND updated_at < NOW() - INTERVAL '10 min')  AS e_stale,
                    (SELECT count(*) FROM messenger_outbox
                      WHERE status = 'PENDING')                      AS m_pending,
                    (SELECT count(*) FROM messenger_outbox
                      WHERE status = 'DLQ')                           AS m_dlq,
                    (SELECT count(*) FROM messenger_outbox
                      WHERE status = 'SENDING'
                        AND updated_at < NOW() - INTERVAL '10 min')  AS m_stale
                """
            )
            if outbox is not None:
                snapshot["email_outbox"] = {
                    "pending": int(outbox["e_pending"] or 0),
                    "dlq": int(outbox["e_dlq"] or 0),
                    "sending_stale": int(outbox["e_stale"] or 0),
                }
                snapshot["messenger_outbox"] = {
                    "pending": int(outbox["m_pending"] or 0),
                    "dlq": int(outbox["m_dlq"] or 0),
                    "sending_stale": int(outbox["m_stale"] or 0),
                }
    except Exception as exc:
        logger.warning("metrics.db_failed", error=str(exc))


async def _read_photo_storage(redis: Any, snapshot: dict) -> None:
    """Photo storage size — read the value written daily by
    ``refresh_photo_storage`` (PHOTO_STORAGE_KEY). Absent key (fresh install
    before the first daily run) → gauge keeps its last value."""
    try:
        raw = await redis.get(PHOTO_STORAGE_KEY)
        if raw is not None:
            value = raw.decode() if isinstance(raw, bytes) else raw
            snapshot["photo_storage_bytes"] = int(value)
    except Exception as exc:
        logger.warning("metrics.photo_storage_read_failed", error=str(exc))


async def refresh_photo_storage(ctx: dict) -> dict:
    """Daily photo-storage size scan → Redis key (no TTL).

    rglob/stat по всем оригиналам — дорогая операция на большом хранилище:
    выполняется раз в сутки (cron 04:35, после cleanup_deleted_photos в 04:00),
    а не на каждом 30-секундном refresh_custom_metrics. ``run_at_startup``
    даёт первое значение сразу после рестарта воркера (один проход на деплой).
    """
    redis = ctx["redis"]
    loop = asyncio.get_running_loop()
    total = await loop.run_in_executor(None, _dir_size_bytes, PHOTOS_ORIGINALS_DIR)
    try:
        await redis.set(PHOTO_STORAGE_KEY, str(total))
    except Exception as exc:
        logger.warning("metrics.photo_storage_publish_failed", error=str(exc))
    logger.info("metrics.photo_storage_refreshed", bytes=total)
    return {"photo_storage_bytes": total}


async def _collect_arq_job_accounting(redis: Any, snapshot: dict) -> None:
    """ARQ job accounting — HGETALL the worker-written hashes. Keys carry the
    cumulative counts; the API hydrates deltas into Prometheus counters."""
    try:
        jobs_raw = await redis.hgetall(ARQ_JOBS_KEY)
        time_raw = await redis.hgetall(ARQ_JOB_TIME_KEY)
        snapshot["arq_jobs"] = {
            k.decode() if isinstance(k, bytes) else k: int(v) for k, v in jobs_raw.items()
        }
        snapshot["arq_job_ms"] = {
            k.decode() if isinstance(k, bytes) else k: int(v) for k, v in time_raw.items()
        }
    except Exception as exc:
        logger.warning("metrics.arq_jobs_failed", error=str(exc))


async def _collect_integration_health(redis: Any, snapshot: dict) -> None:
    """Collect current integration results plus persistent probe metadata."""
    try:
        from app.worker.tasks.integration_health import (
            INTEGRATION_HEALTH_KEY,
            INTEGRATION_PROBE_STATE_KEY,
        )

        state_raw = await redis.hgetall(INTEGRATION_PROBE_STATE_KEY)
        if not state_raw:
            # Rolling-upgrade fallback until the first new probe generation.
            integ_raw = await redis.hgetall(INTEGRATION_HEALTH_KEY)
            snapshot["integrations"] = {
                k.decode() if isinstance(k, bytes) else k: int(v) for k, v in integ_raw.items()
            }
            return

        decoded = {
            k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in state_raw.items()
        }
        expected: dict[str, int] = {}
        attempts: dict[str, float] = {}
        completed: dict[str, float] = {}
        results: dict[str, int] = {}
        now = time.time()
        for field, value in decoded.items():
            try:
                name, kind = field.rsplit(":", 1)
                if kind == "expected":
                    expected[name] = int(value)
                elif kind == "last_attempt":
                    attempts[name] = float(value)
                elif kind == "last_completed":
                    completed[name] = float(value)
                elif kind == "result":
                    expires_at = float(decoded.get(f"{name}:result_expires_at", 0))
                    if expires_at > now:
                        results[name] = int(value)
            except (TypeError, ValueError):
                continue

        snapshot["integrations"] = results
        snapshot["integration_expected"] = expected
        snapshot["integration_last_attempt"] = attempts
        snapshot["integration_last_completed"] = completed
    except Exception as exc:
        logger.warning("metrics.integrations_failed", error=str(exc))


async def refresh_custom_metrics(ctx: dict) -> dict:
    """Refresh custom gauges and store the snapshot in Redis.

    Thin orchestrator: delegates each metric group to a dedicated ``_collect_*``
    coroutine (all swallow their own errors so one failure never poisons the
    whole snapshot). See the per-collector docstrings for the data sources.
    """
    redis = ctx["redis"]
    pool = ctx.get("pg_pool")

    snapshot: dict[str, float | int | dict | str] = {}

    await _collect_audit_depths(redis, snapshot)
    await _collect_audit_push_accounting(redis, snapshot)
    await _collect_worker_heartbeat(redis, snapshot)
    await _collect_arq_queue_depth(redis, snapshot)
    await _collect_sse_connections(redis, snapshot)
    await _collect_db_gauges(pool, snapshot)
    await _read_photo_storage(redis, snapshot)
    await _collect_arq_job_accounting(redis, snapshot)
    await _collect_integration_health(redis, snapshot)

    # Freshness describes a completed collection, not when a potentially slow
    # collection started. Keep the ISO field for existing API/debug consumers
    # and publish an explicit numeric value for Prometheus.
    completed_at = datetime.now(tz=UTC)
    snapshot["generated_at"] = completed_at.isoformat()
    snapshot["generated_at_seconds"] = completed_at.timestamp()

    # Persist the snapshot for the API process to consume
    try:
        await redis.set(METRICS_SNAPSHOT_KEY, json.dumps(snapshot, default=str), ex=300)
    except Exception as exc:
        logger.warning("metrics.snapshot_publish_failed", error=str(exc))

    logger.info("metrics.refreshed", keys=list(snapshot.keys()))
    return snapshot


async def worker_heartbeat(ctx: dict) -> None:
    """Write TTL-bound keys to Redis so healthchecks can verify the ARQ loop is alive.

    Runs every 30 seconds via cron. Writes two keys:

    * ``arq:heartbeat`` (value ``"1"``, TTL 90s) — consumed by the Docker
      healthcheck; absence means the worker is stuck or dead.
    * ``arq:heartbeat:mtime`` (value = unix timestamp, TTL 90s) — read by
      ``refresh_custom_metrics`` into ``portal_worker_last_heartbeat_seconds``
      for age-based alerting. The timestamp lets Prometheus compute the age via
      ``time() - gauge``, which is impossible with the pure TTL key alone.

    Both keys expire after ``WORKER_HEARTBEAT_TTL`` seconds (90 s).
    """
    redis = ctx["redis"]
    now = int(time.time())
    pipe = redis.pipeline()
    pipe.set(WORKER_HEARTBEAT_KEY, "1", ex=WORKER_HEARTBEAT_TTL)
    pipe.set(WORKER_HEARTBEAT_MTIME_KEY, str(now), ex=WORKER_HEARTBEAT_TTL)
    await pipe.execute()
