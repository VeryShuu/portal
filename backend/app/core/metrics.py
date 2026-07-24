"""Custom Prometheus metrics for the portal.

Metrics are exposed via the standard ``/metrics`` endpoint provided by
``prometheus_fastapi_instrumentator``.  Updates are pushed periodically by an
ARQ cron job — see ``app.worker.tasks.metrics``.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- gauges (refreshed periodically by ARQ cron) ---------------------------

sse_connections = Gauge(
    "portal_sse_connections",
    "Number of currently open SSE notification streams (per user, summed).",
)

audit_queue_depth = Gauge(
    "portal_audit_queue_depth",
    "Number of audit events pending in the Redis batch queue.",
)

audit_processing_depth = Gauge(
    "portal_audit_processing_depth",
    "Number of audit events currently being processed by the flush worker.",
)

worker_last_heartbeat = Gauge(
    "portal_worker_last_heartbeat_seconds",
    "Unix timestamp of the last ARQ worker heartbeat (cron worker_heartbeat, "
    "every 30s). Compute age via ``time() - portal_worker_last_heartbeat_seconds``. "
    "A growing age means the worker is stuck or dead — basis for PortalWorkerDown.",
)

# --- DB connection pool (SQLAlchemy AsyncAdaptedQueuePool, API process) -----
# Unlike the gauges above (hydrated from the worker's Redis snapshot), the pool
# is per-process state of the API. It is read directly from ``engine.pool`` on
# each /metrics scrape (see middleware/metrics.py), not from Redis.
#
# in_use = checked out (a request holds the connection); idle = checked in.
# Compare in_use to portal_db_pool_limit (= db_pool_size + db_max_overflow) for
# saturation — a connection leak (unclosed SQLAlchemy session) surfaces here
# before it shows up in pg_stat_activity.
db_pool_size = Gauge(
    "portal_db_pool_size",
    "SQLAlchemy pool connections in the API process by state "
    "(in_use = checked out; idle = checked in).",
    labelnames=("state",),
)
db_pool_limit = Gauge(
    "portal_db_pool_limit",
    "Max connections the API pool will open (db_pool_size + db_max_overflow). "
    'Divide portal_db_pool_size{state="in_use"} by this for saturation ratio.',
)

active_users_1h = Gauge(
    "portal_active_users_last_1h",
    "Distinct users that produced at least one audit event in the last hour.",
)

photo_storage_bytes = Gauge(
    "portal_photo_storage_bytes",
    "Total bytes stored under /data/photos/originals (refreshed daily).",
)

# --- outbox gauges (refreshed by ARQ cron, hydrated from Redis snapshot) ---
# Transactional outbox health: queue depth, DLQ accumulation, stuck-SENDING.
# Without these, email/MAX delivery failures are invisible until users complain.
email_outbox_pending = Gauge(
    "portal_email_outbox_pending",
    "Email outbox rows in PENDING status (awaiting dispatch).",
)
email_outbox_dlq = Gauge(
    "portal_email_outbox_dlq",
    "Email outbox rows in DLQ status (exhausted retries, dead-lettered).",
)
email_outbox_sending_stale = Gauge(
    "portal_email_outbox_sending_stale",
    "Email outbox rows stuck in SENDING > 10 min (worker crash mid-dispatch).",
)
messenger_outbox_pending = Gauge(
    "portal_messenger_outbox_pending",
    "Messenger outbox (MAX) rows in PENDING status (awaiting dispatch).",
)
messenger_outbox_dlq = Gauge(
    "portal_messenger_outbox_dlq",
    "Messenger outbox (MAX) rows in DLQ status (exhausted retries).",
)
messenger_outbox_sending_stale = Gauge(
    "portal_messenger_outbox_sending_stale",
    "Messenger outbox rows stuck in SENDING > 10 min (worker crash mid-dispatch).",
)

# --- integration health (refreshed by probe_integrations cron) ---
# 1 = reachable, 0 = down. Gated: only set when the integration is configured.
integration_up = Gauge(
    "portal_integration_up",
    "Integration reachability probe (1 = up, 0 = down).",
    labelnames=("integration",),
)

# --- synthetic user-flow probes (refreshed by run_synthetic_probe cron) ---
# 1 = flow succeeded (login + SPA load), 0 = failed. Gated: absent when
# PROBE_ADMIN_EMAIL/PASSWORD are not configured.
synthetic_probe_up = Gauge(
    "portal_synthetic_probe_up",
    "Synthetic user-flow probe (1 = ok, 0 = failed).",
    labelnames=("flow",),
)
synthetic_probe_duration = Gauge(
    "portal_synthetic_probe_duration_seconds",
    "Synthetic user-flow probe wall-clock duration in seconds.",
    labelnames=("flow",),
)

kb_articles_total = Gauge(
    "portal_kb_articles_total",
    "Total non-deleted KB articles by status.",
    labelnames=("status",),
)

news_published_total = Gauge(
    "portal_news_published_total",
    "Number of news items by status.",
    labelnames=("status",),
)

users_total = Gauge(
    "portal_users_total",
    "Total user accounts by auth_source.",
    labelnames=("auth_source",),
)

# --- counters (incremented inline by application code) ---------------------

audit_events_pushed = Counter(
    "portal_audit_events_pushed_total",
    "Audit events pushed to the Redis queue.",
    labelnames=("event_type",),
)

# --- ARQ worker job metrics (cross-process: worker → Redis → API /metrics) --
# Worker increments these via Redis (hincrby) in track_arq_job; the API process
# hydrates them into these Prometheus objects on each /metrics scrape
# (see middleware/metrics.py::hydrate_custom_metrics).
arq_jobs_total = Counter(
    "portal_arq_jobs_total",
    "ARQ worker jobs processed, by function and outcome.",
    labelnames=("function", "status"),
)

arq_job_duration = Histogram(
    "portal_arq_job_duration_seconds",
    "ARQ worker job wall-clock duration in seconds.",
    labelnames=("function",),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)

# Depth of the ARQ pending-queue (Redis ZSET ``arq:queue``, read via ZCARD in
# refresh_custom_metrics). A growing depth means the worker is not keeping up
# (slow/dead jobs, or the worker is down while jobs keep being enqueued) — basis
# for PortalArqQueueBacklog. Distinct from arq_jobs_total (cumulative processed).
arq_queue_depth = Gauge(
    "portal_arq_queue_depth",
    "Number of jobs pending in the ARQ queue (Redis ZSET arq:queue).",
)
