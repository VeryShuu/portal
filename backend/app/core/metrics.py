"""Custom Prometheus metrics for the portal.

Metrics are exposed via the standard ``/metrics`` endpoint provided by
``prometheus_fastapi_instrumentator``.  Updates are pushed periodically by an
ARQ cron job — see ``app.worker.tasks.metrics``.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

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

active_users_1h = Gauge(
    "portal_active_users_last_1h",
    "Distinct users that produced at least one audit event in the last hour.",
)

photo_storage_bytes = Gauge(
    "portal_photo_storage_bytes",
    "Total bytes stored under /data/photos/originals (refreshed daily).",
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
