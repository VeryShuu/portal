import asyncio
import json
import os
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from typing import cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator.metrics import Info
from sqlalchemy.pool import QueuePool

from app.core import metrics as _metrics_mod
from app.core.constants import NOTIFICATIONS_STREAM_PATH
from app.core.logging import get_logger
from app.worker.tasks.metrics import METRICS_SNAPSHOT_KEY

logger = get_logger(__name__)

# Label-сеты, выставленные последним снапшотом (для очистки исчезнувших:
# prometheus_client сам не удаляет label-комбинации gauge'ей — убранная из
# конфигурации интеграция/флоу навсегда оставалась бы с последним значением).
_integration_seen: set[str] = set()
_integration_expected_seen: set[str] = set()
_integration_result_available_seen: set[str] = set()
_integration_attempt_seen: set[str] = set()
_integration_completed_seen: set[str] = set()
_synthetic_up_seen: set[str] = set()
_synthetic_duration_seen: set[str] = set()


async def _hydrate_db_pool() -> None:
    """DB pool — per-process state of the API, NOT in the Redis snapshot.

    Read directly from the SQLAlchemy engine on each scrape. Lazy import to
    avoid import-time coupling. Caller wraps in try/except → never breaks /metrics.
    """
    from app.core.config import get_settings as _get_settings
    from app.core.database import engine as _engine

    _cfg = _get_settings()
    _metrics_mod.db_pool_limit.set(_cfg.db_pool_size + _cfg.db_max_overflow)
    # checkedout()/checkedin() — методы QueuePool (create_async_engine создаёт
    # AsyncAdaptedQueuePool, который проксирует их в рантайме). SA стабы
    # типизируют engine.pool как базовый Pool, у которого этих методов нет;
    # cast(QueuePool) восстанавливает доступ (smoke-tested: реальный тип —
    # AsyncAdaptedQueuePool, методы возвращают int).
    pool = cast(QueuePool, _engine.pool)
    _metrics_mod.db_pool_size.labels(state="in_use").set(pool.checkedout())
    _metrics_mod.db_pool_size.labels(state="idle").set(pool.checkedin())
    _metrics_mod.db_pool_update_timestamp.set(time.time())


# Each uvicorn worker refreshes its own pool series on this cadence, so per-pid
# liveall rows stay fresh for EVERY process regardless of which one serves the
# /metrics scrape (MON-09: mostrecent exposed only the scrape-serving process).
DB_POOL_REFRESH_INTERVAL_SECONDS = 10.0

_pool_updater_task: asyncio.Task[None] | None = None


async def refresh_db_pool_forever(
    interval: float = DB_POOL_REFRESH_INTERVAL_SECONDS,
) -> None:
    """Периодическое обновление pool-гаuges текущего API-процесса.

    Гидратация на scrape пишет только обслуживший процесс; остальные воркеры
    обновляются здесь, поэтому их liveall-ряды не протухают. Ошибка одного
    обновления не завершает цикл — следующий тик повторит попытку.
    """
    while True:
        try:
            await _hydrate_db_pool()
        except Exception as exc:  # никогда не ронять фоновый цикл
            logger.warning(
                "metrics.db_pool_refresh_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        await asyncio.sleep(interval)


def start_db_pool_updater() -> None:
    """Запустить фоновый обновитель пула (один на процесс, идемпотентно)."""
    global _pool_updater_task
    if _pool_updater_task is None or _pool_updater_task.done():
        _pool_updater_task = asyncio.create_task(refresh_db_pool_forever())


async def stop_db_pool_updater() -> None:
    """Остановить фоновый обновитель пула (graceful shutdown)."""
    global _pool_updater_task
    if _pool_updater_task is not None:
        _pool_updater_task.cancel()
        with suppress(asyncio.CancelledError):
            await _pool_updater_task
        _pool_updater_task = None


def _hydrate_scalar_gauges(snap: dict) -> None:
    """Set simple scalar gauges from snapshot keys (each guarded for presence)."""
    _gauge_map = {
        "audit_queue_depth": _metrics_mod.audit_queue_depth,
        "audit_processing_depth": _metrics_mod.audit_processing_depth,
        "worker_heartbeat_ts": _metrics_mod.worker_last_heartbeat,
        "generated_at_seconds": _metrics_mod.metrics_snapshot_generated,
        "arq_queue_depth": _metrics_mod.arq_queue_depth,
        "sse_connections": _metrics_mod.sse_connections,
        "active_users_1h": _metrics_mod.active_users_1h,
        "photo_storage_bytes": _metrics_mod.photo_storage_bytes,
        "helpdesk_archive_backlog": _metrics_mod.helpdesk_archive_backlog,
    }
    for key, gauge in _gauge_map.items():
        if key in snap:
            gauge.set(float(snap[key]))


def _hydrate_labeled_counters(snap: dict) -> None:
    """Set labeled gauges driven by snapshot sub-dicts (status/src breakdowns)."""
    for status, value in (snap.get("kb_articles_total") or {}).items():
        _metrics_mod.kb_articles_total.labels(status=status).set(float(value))
    for status, value in (snap.get("news_published_total") or {}).items():
        _metrics_mod.news_published_total.labels(status=status).set(float(value))
    for src, value in (snap.get("users_total") or {}).items():
        _metrics_mod.users_total.labels(auth_source=src).set(float(value))


def _prune_gauge_labels(gauge: Gauge, seen: set[str], current: set[str]) -> None:
    """Убрать label-сеты, исчезнувшие из снапшота (гидратация следующего scrape).

    Однопроцессный режим: gauge.remove() — серия исчезает из экспозиции.
    Multiproc: remove() в prometheus_client не реализован для mmap-файлов —
    вместо этого выставляем NaN: mostrecent-агрегация берёт самую свежую запись,
    NaN со свежим timestamp затмевает устаревшее значение из любого per-pid
    файла; сравнения ``== 0``/``== 1`` в алертах дают false (тишина), панели
    показывают «no data».
    """
    for stale in seen - current:
        try:
            if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
                gauge.labels(stale).set(float("nan"))
            else:
                gauge.remove(stale)
        except (KeyError, ValueError):  # серия уже удалена/не существует
            pass
    seen.clear()
    seen.update(current)


def _hydrate_audit_push(snap: dict) -> None:
    """Audit push metric — абсолют из Redis-кумулятива.

    Значение кросс-процессное (источник — Redis-хэш ``audit:metrics:pushed``,
    HINCRBY в services/audit.py), поэтому выставляем абсолют ``set()`` в
    gauge с mostrecent-агрегацией (см. core/metrics.py): работает одинаково
    при любом числе uvicorn-воркеров. Прежний per-process delta-инкремент
    Counter'а в multiproc-режиме двоил бы кумулятив.
    """
    for event_type, value in (snap.get("audit_pushed") or {}).items():
        try:
            current = float(value)
        except (TypeError, ValueError):
            continue
        _metrics_mod.audit_events_pushed.labels(event_type=event_type).set(current)


def _hydrate_arq_jobs(snap: dict) -> None:
    """ARQ job metric — абсолют из Redis-кумулятива.

    snapshot key "arq_jobs" maps "{function}:{status}" -> cumulative count.
    """
    for field, value in (snap.get("arq_jobs") or {}).items():
        try:
            func_name, status = field.rsplit(":", 1)
            current = float(value)
        except (TypeError, ValueError):
            continue
        _metrics_mod.arq_jobs_total.labels(function=func_name, status=status).set(current)


def _hydrate_arq_job_duration(snap: dict) -> None:
    """ARQ job duration — кумулятивные мс per function, абсолют ``set()``.

    snapshot key "arq_job_ms" maps "{function}:sum" -> cumulative milliseconds.
    Поля "{function}:count" не читаются: число задач даёт
    portal_arq_jobs_total по terminal-статусам.
    """
    ms = snap.get("arq_job_ms") or {}
    for field, value in ms.items():
        if not field.endswith(":sum"):
            continue
        try:
            current = float(value)
        except (TypeError, ValueError):
            continue
        _metrics_mod.arq_job_duration_ms_total.labels(function=field[:-4]).set(current)


def _hydrate_outbox_gauges(snap: dict) -> None:
    """Outbox gauges — plain set() (no labels, cumulative counts)."""
    for kind in ("pending", "dlq", "sending_stale"):
        eo = snap.get("email_outbox") or {}
        if kind in eo:
            getattr(_metrics_mod, f"email_outbox_{kind}").set(float(eo[kind]))
        mo = snap.get("messenger_outbox") or {}
        if kind in mo:
            getattr(_metrics_mod, f"messenger_outbox_{kind}").set(float(mo[kind]))


def _set_and_prune_integration_gauge(
    gauge: Gauge,
    seen: set[str],
    values: dict,
) -> None:
    current = set(values)
    for integration, value in values.items():
        gauge.labels(integration).set(float(value))
    _prune_gauge_labels(gauge, seen, current)


def _hydrate_integration_probes(snap: dict) -> None:
    """Hydrate results and persistent expectation/freshness metadata."""
    results = snap.get("integrations") or {}
    expected = snap.get("integration_expected") or {}
    _set_and_prune_integration_gauge(
        _metrics_mod.integration_up,
        _integration_seen,
        results,
    )
    _set_and_prune_integration_gauge(
        _metrics_mod.integration_expected,
        _integration_expected_seen,
        expected,
    )
    _set_and_prune_integration_gauge(
        _metrics_mod.integration_result_available,
        _integration_result_available_seen,
        {name: int(name in results) for name in expected},
    )
    _set_and_prune_integration_gauge(
        _metrics_mod.integration_probe_last_attempt,
        _integration_attempt_seen,
        snap.get("integration_last_attempt") or {},
    )
    _set_and_prune_integration_gauge(
        _metrics_mod.integration_probe_last_completed,
        _integration_completed_seen,
        snap.get("integration_last_completed") or {},
    )


def _hydrate_snapshot(snap: dict) -> None:
    """Apply every snapshot-driven metric group to Prometheus gauges.

    Each group is independent; an exception in one does not abort the others
    (the caller wraps the whole call in try/except).
    """
    _hydrate_scalar_gauges(snap)
    _hydrate_labeled_counters(snap)
    _hydrate_arq_jobs(snap)
    _hydrate_arq_job_duration(snap)
    _hydrate_audit_push(snap)
    _hydrate_outbox_gauges(snap)
    _hydrate_integration_probes(snap)


async def hydrate_custom_metrics(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Pull the latest snapshot from Redis into Prometheus gauges before scrape."""
    if request.url.path != "/metrics":
        return await call_next(request)

    # Set pessimistically for this scrape. A successful current read below is
    # the only path that changes the value to 1; stale in-memory business
    # gauges therefore cannot hide Redis/key/JSON/hydration failures.
    _metrics_mod.metrics_snapshot_read_success.set(0)
    try:
        await _hydrate_db_pool()

        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            raw = await redis.get(METRICS_SNAPSHOT_KEY)
            if raw:
                snap = json.loads(raw)
                if not isinstance(snap, dict):
                    raise ValueError("metrics snapshot must be a JSON object")
                _hydrate_snapshot(snap)
                _metrics_mod.metrics_snapshot_read_success.set(1)
    except Exception as exc:  # pragma: no cover - never break /metrics
        logger.warning(
            "metrics.hydrate_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
    return await call_next(request)


async def _require_metrics_token(
    x_metrics_token: str = Header(default=""),
    authorization: str = Header(default=""),
) -> None:
    """Validate the scrape token protecting ``/metrics``.

    Accepts the token via either of two headers (both checked, either suffices):

    * ``Authorization: Bearer <token>`` — canonical Prometheus transport
      (``prometheus.yml::scrape_configs.authorization.credentials`` sends this).
    * ``X-Metrics-Token: <token>`` — legacy/custom header, convenient for
      ad-hoc ``curl`` checks and operator scripts.

    If ``system.json::metrics_token`` is empty, ``/metrics`` is open (closed
    perimeter/VPN assumption). When set, a wrong/missing token → 403.
    """
    from app.core.system_config import load_system_settings

    tok = load_system_settings().metrics_token
    if not tok:
        return

    bearer = ""
    if authorization.lower().startswith("bearer "):
        bearer = authorization[7:]

    provided = bearer or x_metrics_token
    if not provided or not secrets.compare_digest(provided, tok):
        raise HTTPException(status_code=403, detail="Forbidden")


def _latency_excluding_sse(buckets: Sequence[float]) -> Callable[[Info], None]:
    """``latency()``-гистограмма, пропускающая SSE-стрим уведомлений.

    Длительность SSE-запроса = время жизни соединения (~60 c, потом клиент
    переподключается), а не латентность обработки: попав в гистограмму, стрим
    оккупирует верхние бакеты и ломает p99-панели и recording-правила
    ``portal:http_latency_p*_5m``. Счётчик ``requests()`` не трогаем — error-rate
    стрима (429/503 при исчерпании лимитов/падении Redis) остаётся видимым.
    """
    from prometheus_fastapi_instrumentator.metrics import latency

    # status-лейбл не включаем: статус уже есть у http_requests_total,
    # а latency×status утраивает кардинальность гистограммы.
    base = latency(buckets=buckets, should_include_status=False)

    def instrumentation(info: Info) -> None:
        if info.modified_handler == NOTIFICATIONS_STREAM_PATH:
            return
        if base is not None:
            base(info)

    return instrumentation


def setup_metrics(app: FastAPI) -> None:
    """Instrument the app with Prometheus and expose /metrics endpoint.

    Явный набор метрик вместо дефолтного metrics.default(): дефолт давал
    ДВЕ latency-гистограммы — low-res с лейблами (всего 3 бакета: p99 по ней
    бессмыслен) и high-res БЕЗ лейблов (нельзя разбить по endpoint). Кастомная
    latency() — нормальные бакеты + handler/method; highr-дубль не создаётся.
    """
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_fastapi_instrumentator.metrics import requests

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
    )
    instrumentator.add(requests())
    instrumentator.add(
        _latency_excluding_sse(
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 30, 60),
        )
    )
    instrumentator.instrument(app)
    instrumentator.expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        dependencies=[Depends(_require_metrics_token)],
    )
    app.middleware("http")(hydrate_custom_metrics)
