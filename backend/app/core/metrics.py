"""Custom Prometheus metrics for the portal.

Metrics are exposed via the standard ``/metrics`` endpoint provided by
``prometheus_fastapi_instrumentator``.  Updates are pushed periodically by an
ARQ cron job — see ``app.worker.tasks.metrics``.

Multiprocess mode (uvicorn ``--workers 2`` на проде)
----------------------------------------------------
Образ backend'а выставляет ``PROMETHEUS_MULTIPROC_DIR``: prometheus_client
переключается на per-process mmap-файлы, а ``/metrics`` (instrumentator
``expose()``) агрегирует их через ``MultiProcessCollector``. Без этого каждый
воркер держал собственный реестр, и scrape видел состояние ОДНОГО случайного
воркера — RED/SLO-цифры были шумом от половины трафика (аудит 2026-08).

Все snapshot-driven gauge'и объявлены с ``multiprocess_mode="mostrecent"``:
гидратирует только воркер, обслуживший scrape, а коллектор берёт самую свежую
запись (pid-лейбл срезается). В однопроцессном dev-режиме (без env) параметр
принимается и игнорируется.

Три метрики ``*_total`` ниже — ЭТО GAUGE, НЕ COUNTER: их значения — кумулятивные
абсолюты из Redis-снапшота, выставляемые ``set()`` на каждом scrape.
``rate()``/``increase()`` работают по монотонно растущим gauge'ям, поэтому
алерты и панели не меняются; суффикс ``_total`` сохранён ради совместимости
с существующими правилами/дашбордами.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

# --- gauges (refreshed periodically by ARQ cron) ---------------------------

sse_connections = Gauge(
    "portal_sse_connections",
    "Number of currently open SSE notification streams (per user, summed).",
    multiprocess_mode="mostrecent",
)

audit_queue_depth = Gauge(
    "portal_audit_queue_depth",
    "Number of audit events pending in the Redis batch queue.",
    multiprocess_mode="mostrecent",
)

backend_ready = Gauge(
    "portal_backend_ready",
    "1 if the last /ready evaluation passed, 0 otherwise (PA-023). Docker "
    "health status has no runtime automation behind it (restart policy acts "
    'on exit only, no LB eviction), and up{job="portal"} proves only that '
    "the process is alive — this gauge exposes alive-but-unhealthy states. "
    "Refreshed on every /ready call (Docker healthcheck interval). If the "
    "process dies outright, the gauge freezes and PortalBackendDown (up==0) "
    "covers it instead.",
    multiprocess_mode="mostrecent",
)

audit_processing_depth = Gauge(
    "portal_audit_processing_depth",
    "Number of audit events currently being processed by the flush worker.",
    multiprocess_mode="mostrecent",
)

worker_last_heartbeat = Gauge(
    "portal_worker_last_heartbeat_seconds",
    "Unix timestamp of the last ARQ worker heartbeat (cron worker_heartbeat, "
    "every 30s). Compute age via ``time() - portal_worker_last_heartbeat_seconds``. "
    "A growing age means the worker is stuck or dead — basis for PortalWorkerDown.",
    multiprocess_mode="mostrecent",
)

metrics_snapshot_generated = Gauge(
    "portal_metrics_snapshot_generated_timestamp_seconds",
    "Unix timestamp when the worker completed and published the latest Redis "
    "metrics snapshot. Age detects a stopped refresh loop even while old "
    "snapshot-driven gauges remain in API worker memory.",
    multiprocess_mode="mostrecent",
)
metrics_snapshot_read_success = Gauge(
    "portal_metrics_snapshot_read_success",
    "1 if the current /metrics scrape read and hydrated a valid Redis metrics "
    "snapshot, 0 if Redis, the key, JSON, or hydration was unavailable.",
    multiprocess_mode="mostrecent",
)

# --- DB connection pool (SQLAlchemy AsyncAdaptedQueuePool, API process) -----
# Unlike the gauges above (hydrated from the worker's Redis snapshot), the pool
# is per-process state of the API. Every uvicorn worker refreshes its OWN series
# from a background task (DB_POOL_REFRESH_INTERVAL_SECONDS, wired in lifespan)
# plus opportunistically on each /metrics scrape (see middleware/metrics.py) —
# saturation of a worker that did not serve the scrape is visible too (MON-09).
# multiprocess_mode="liveall": каждая серия получает pid-лейбл на экспозиции,
# ряды умершего воркера исчезают сами; mostrecent показывал бы состояние
# одного случайного процесса и прятал leak соседнего.
# in_use = checked out (a request holds the connection); idle = checked in.
# Compare in_use to portal_db_pool_limit (= db_pool_size + db_max_overflow) for
# saturation — a connection leak (unclosed SQLAlchemy session) surfaces here
# before it shows up in pg_stat_activity.
db_pool_size = Gauge(
    "portal_db_pool_size",
    "SQLAlchemy pool connections in the API process by state "
    "(in_use = checked out; idle = checked in). Per-pid series: one per "
    "uvicorn worker.",
    labelnames=("state",),
    multiprocess_mode="liveall",
)
db_pool_limit = Gauge(
    "portal_db_pool_limit",
    "Max connections the API pool will open (db_pool_size + db_max_overflow). "
    'Divide portal_db_pool_size{state="in_use"} by this for per-process '
    "saturation ratio.",
    multiprocess_mode="liveall",
)
db_pool_update_timestamp = Gauge(
    "portal_db_pool_update_timestamp_seconds",
    "Unix timestamp when this API process last refreshed its pool gauges "
    "(background task, every 10s). Growing age means a stuck event loop in a "
    "live process, or a hard-killed worker whose rows linger until backend "
    "restart (graceful shutdown removes them via mark_process_dead).",
    multiprocess_mode="liveall",
)

active_users_1h = Gauge(
    "portal_active_users_last_1h",
    "Distinct users that produced at least one audit event in the last hour.",
    multiprocess_mode="mostrecent",
)

photo_storage_bytes = Gauge(
    "portal_photo_storage_bytes",
    "Total bytes stored under /data/photos/originals (refreshed daily at 04:35 "
    "by ARQ cron refresh_photo_storage + at worker startup; the storage-collector "
    "textfile metric portal_storage_folder_bytes{folder=...photos/originals} "
    "covers the same folder every 5 min).",
    multiprocess_mode="mostrecent",
)

helpdesk_archive_backlog = Gauge(
    "portal_helpdesk_archive_backlog",
    "Closed helpdesk tickets waiting to be moved to the immutable archive.",
    multiprocess_mode="mostrecent",
)

# --- outbox gauges (refreshed by ARQ cron, hydrated from Redis snapshot) ---
# Transactional outbox health: queue depth, DLQ accumulation, stuck-SENDING.
# Without these, email/MAX delivery failures are invisible until users complain.
email_outbox_pending = Gauge(
    "portal_email_outbox_pending",
    "Email outbox rows in PENDING status (awaiting dispatch).",
    multiprocess_mode="mostrecent",
)
email_outbox_dlq = Gauge(
    "portal_email_outbox_dlq",
    "Email outbox rows in DLQ status (exhausted retries, dead-lettered).",
    multiprocess_mode="mostrecent",
)
email_outbox_sending_stale = Gauge(
    "portal_email_outbox_sending_stale",
    "Email outbox rows stuck in SENDING > 10 min (worker crash mid-dispatch).",
    multiprocess_mode="mostrecent",
)
messenger_outbox_pending = Gauge(
    "portal_messenger_outbox_pending",
    "Messenger outbox (MAX) rows in PENDING status (awaiting dispatch).",
    multiprocess_mode="mostrecent",
)
messenger_outbox_dlq = Gauge(
    "portal_messenger_outbox_dlq",
    "Messenger outbox (MAX) rows in DLQ status (exhausted retries).",
    multiprocess_mode="mostrecent",
)
messenger_outbox_sending_stale = Gauge(
    "portal_messenger_outbox_sending_stale",
    "Messenger outbox rows stuck in SENDING > 10 min (worker crash mid-dispatch).",
    multiprocess_mode="mostrecent",
)

# --- integration health (refreshed by probe_integrations cron) ---
# 1 = reachable, 0 = down. Gated: only set when the integration is configured.
integration_up = Gauge(
    "portal_integration_up",
    "Integration reachability probe (1 = up, 0 = down).",
    labelnames=("integration",),
    multiprocess_mode="mostrecent",
)

integration_expected = Gauge(
    "portal_integration_expected",
    "1 when an integration probe is expected, 0 when disabled or unconfigured.",
    labelnames=("integration",),
    multiprocess_mode="mostrecent",
)
integration_result_available = Gauge(
    "portal_integration_result_available",
    "1 when the latest integration result is still within its validity window.",
    labelnames=("integration",),
    multiprocess_mode="mostrecent",
)
integration_probe_last_attempt = Gauge(
    "portal_integration_probe_last_attempt_timestamp_seconds",
    "Unix timestamp when the integration probe was last started.",
    labelnames=("integration",),
    multiprocess_mode="mostrecent",
)
integration_probe_last_completed = Gauge(
    "portal_integration_probe_last_completed_timestamp_seconds",
    "Unix timestamp when the integration probe last completed and published.",
    labelnames=("integration",),
    multiprocess_mode="mostrecent",
)

kb_articles_total = Gauge(
    "portal_kb_articles_total",
    "Total non-deleted KB articles by status.",
    labelnames=("status",),
    multiprocess_mode="mostrecent",
)

news_published_total = Gauge(
    "portal_news_published_total",
    "Number of news items by status.",
    labelnames=("status",),
    multiprocess_mode="mostrecent",
)

users_total = Gauge(
    "portal_users_total",
    "Total user accounts by auth_source.",
    labelnames=("auth_source",),
    multiprocess_mode="mostrecent",
)

# --- cumulative gauges (cross-process: Redis-кумулятив → set() на scrape) ----
# Прод крутит несколько uvicorn-воркеров. Источники ниже пишут кумулятивы через
# HINCRBY в Redis-хэши (audit — services/audit.py::audit:metrics:pushed,
# ARQ — worker/tasks/metrics.py::track_arq_job → arq:metrics:*), а API-процесс
# на каждом scrape выставляет АБСОЛЮТ в gauge с mostrecent-агрегацией
# (middleware/metrics.py). Это gauge, а не counter: в multiproc-режиме counter
# агрегируется суммой по per-pid файлам, и per-process delta-инкременты
# двоили бы кумулятив; rate()/increase() по монотонному gauge работают как
# раньше. Суффикс _total сохранён для совместимости с алертами/панелями.

audit_events_pushed = Gauge(
    "portal_audit_events_pushed_total",
    "Audit events pushed to the Redis queue (cumulative absolute, gauge — see module docstring).",
    labelnames=("event_type",),
    multiprocess_mode="mostrecent",
)

arq_jobs_total = Gauge(
    "portal_arq_jobs_total",
    "ARQ worker jobs processed, by function and outcome (cumulative absolute, "
    "gauge — see module docstring).",
    labelnames=("function", "status"),
    multiprocess_mode="mostrecent",
)

# Кумулятивная сумма длительностей задач (мс) по функциям. Per-job наблюдения
# в Redis-hash агрегации недоступны (HINCRBY копит только суммы), поэтому
# гистограмма невозможна без искажений; средняя = rate(..._ms_total) /
# rate(portal_arq_jobs_total) по завершённым статусам.
arq_job_duration_ms_total = Gauge(
    "portal_arq_job_duration_ms_total",
    "Cumulative wall-clock duration of ARQ jobs in milliseconds by function "
    "(cumulative absolute, gauge — see module docstring). "
    'Average seconds = rate(..._ms_total) / rate(portal_arq_jobs_total{status!="started"}).',
    labelnames=("function",),
    multiprocess_mode="mostrecent",
)

# Depth of the ARQ pending-queue (Redis ZSET ``arq:queue``, read via ZCARD in
# refresh_custom_metrics). A growing depth means the worker is not keeping up
# (slow/dead jobs, or the worker is down while jobs keep being enqueued) — basis
# for PortalArqQueueBacklog. Distinct from arq_jobs_total (cumulative processed).
arq_queue_depth = Gauge(
    "portal_arq_queue_depth",
    "Number of jobs pending in the ARQ queue (Redis ZSET arq:queue).",
    multiprocess_mode="mostrecent",
)

# --- approvals (согласование 1С): бизнес-счётчик, инкремент в API-процессе ---
# Обычный Counter (как portal_http_client_requests_total в core/http_metrics):
# источник инкремента — сам API-процесс (scrape-target), multiproc-коллектор
# корректно суммирует per-pid файлы. Redis-кумулятив (см. блок выше) нужен
# только когда значение считает воркер, а выставляет API.
# action ∈ {approve, reject, bulk_approve}; outcome ∈ {ok, error} (у
# bulk_approve ещё {partial} — часть партии согласована).
approvals_actions_total = Counter(
    "portal_approvals_actions_total",
    "Approval actions on 1C documents performed via the portal, by action and "
    "outcome (bulk_approve also has outcome=partial).",
    labelnames=("action", "outcome"),
)
