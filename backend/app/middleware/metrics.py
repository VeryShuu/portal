import json
import secrets
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from app.core import metrics as _metrics_mod
from app.core.logging import get_logger
from app.worker.tasks.metrics import METRICS_SNAPSHOT_KEY

logger = get_logger(__name__)

# Cross-process counter/histogram hydration state.
# Prometheus counters can only be incremented (no .set()), so we track the
# last cumulative value seen from the worker snapshot and apply the delta.
# These dicts persist for the process lifetime (single API process).
_arq_job_last: dict[str, float] = {}
_arq_job_ms_last: dict[str, float] = {}


async def hydrate_custom_metrics(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Pull the latest snapshot from Redis into Prometheus gauges before scrape."""
    if request.url.path == "/metrics":
        try:
            # DB pool — per-process state of the API, NOT in the Redis snapshot.
            # Read directly from the SQLAlchemy engine on each scrape. Lazy import
            # to avoid import-time coupling (same style as load_system_settings
            # below). Wrapped in this try/except → never breaks /metrics.
            from app.core.config import get_settings as _get_settings
            from app.core.database import engine as _engine

            _cfg = _get_settings()
            _metrics_mod.db_pool_limit.set(_cfg.db_pool_size + _cfg.db_max_overflow)
            # checkedout()/checkedin() — methods of QueuePool (AsyncAdaptedQueuePool
            # proxies them at runtime). SQLAlchemy stubs type engine.pool as the
            # base Pool which lacks these, hence the ignore (smoke-tested in the
            # container: type is AsyncAdaptedQueuePool, methods return int).
            _metrics_mod.db_pool_size.labels(state="in_use").set(
                _engine.pool.checkedout()  # type: ignore[attr-defined]
            )
            _metrics_mod.db_pool_size.labels(state="idle").set(
                _engine.pool.checkedin()  # type: ignore[attr-defined]
            )

            redis = getattr(request.app.state, "redis", None)
            if redis is not None:
                raw = await redis.get(METRICS_SNAPSHOT_KEY)
                if raw:
                    snap = json.loads(raw)
                    if "audit_queue_depth" in snap:
                        _metrics_mod.audit_queue_depth.set(float(snap["audit_queue_depth"]))
                    if "audit_processing_depth" in snap:
                        _metrics_mod.audit_processing_depth.set(
                            float(snap["audit_processing_depth"])
                        )
                    if "worker_heartbeat_ts" in snap:
                        _metrics_mod.worker_last_heartbeat.set(float(snap["worker_heartbeat_ts"]))
                    if "arq_queue_depth" in snap:
                        _metrics_mod.arq_queue_depth.set(float(snap["arq_queue_depth"]))
                    if "sse_connections" in snap:
                        _metrics_mod.sse_connections.set(float(snap["sse_connections"]))
                    if "active_users_1h" in snap:
                        _metrics_mod.active_users_1h.set(float(snap["active_users_1h"]))
                    if "photo_storage_bytes" in snap:
                        _metrics_mod.photo_storage_bytes.set(float(snap["photo_storage_bytes"]))
                    for status, value in (snap.get("kb_articles_total") or {}).items():
                        _metrics_mod.kb_articles_total.labels(status=status).set(float(value))
                    for status, value in (snap.get("news_published_total") or {}).items():
                        _metrics_mod.news_published_total.labels(status=status).set(float(value))
                    for src, value in (snap.get("users_total") or {}).items():
                        _metrics_mod.users_total.labels(auth_source=src).set(float(value))

                    # ARQ job counters — delta-increment from the last snapshot.
                    # snapshot key "arq_jobs" maps "{function}:{status}" -> cumulative count.
                    for field, value in (snap.get("arq_jobs") or {}).items():
                        try:
                            func_name, status = field.rsplit(":", 1)
                        except ValueError:
                            continue
                        current = float(value)
                        prev = _arq_job_last.get(field, 0.0)
                        delta = current - prev
                        if delta > 0:
                            _metrics_mod.arq_jobs_total.labels(
                                function=func_name, status=status
                            ).inc(delta)
                        _arq_job_last[field] = current

                    # ARQ job duration histogram — delta-increment of count and sum.
                    # snapshot key "arq_job_ms" maps "{function}:{count|sum}" -> value.
                    ms = snap.get("arq_job_ms") or {}
                    funcs = {f for f in ms if f.endswith(":count") or f.endswith(":sum")}
                    for prefix in {f.rsplit(":", 1)[0] for f in funcs}:
                        try:
                            cur_count = float(ms.get(f"{prefix}:count", 0))
                            cur_sum = float(ms.get(f"{prefix}:sum", 0))
                        except (TypeError, ValueError):
                            continue
                        prev_count = _arq_job_ms_last.get(f"{prefix}:count", 0.0)
                        prev_sum = _arq_job_ms_last.get(f"{prefix}:sum", 0.0)
                        d_count = cur_count - prev_count
                        d_sum_ms = cur_sum - prev_sum
                        if d_count > 0:
                            # Observe average per-job duration for the delta batch.
                            _metrics_mod.arq_job_duration.labels(function=prefix).observe(
                                d_sum_ms / 1000.0 / d_count
                            )
                        _arq_job_ms_last[f"{prefix}:count"] = cur_count
                        _arq_job_ms_last[f"{prefix}:sum"] = cur_sum

                    # Outbox gauges — plain set() (no labels, cumulative counts).
                    for kind in ("pending", "dlq", "sending_stale"):
                        eo = snap.get("email_outbox") or {}
                        if kind in eo:
                            getattr(_metrics_mod, f"email_outbox_{kind}").set(float(eo[kind]))
                        mo = snap.get("messenger_outbox") or {}
                        if kind in mo:
                            getattr(_metrics_mod, f"messenger_outbox_{kind}").set(float(mo[kind]))

                    # Integration probes — 1/0 up/down per integration.
                    for integration, value in (snap.get("integrations") or {}).items():
                        _metrics_mod.integration_up.labels(integration=integration).set(
                            float(value)
                        )

                    # Synthetic probes — "{flow}:ok"/"{flow}:ms" per flow.
                    synth = snap.get("synthetic_probe") or {}
                    flows = {f[:-3] for f in synth if f.endswith(":ok") or f.endswith(":ms")}
                    for flow in flows:
                        if f"{flow}:ok" in synth:
                            _metrics_mod.synthetic_probe_up.labels(flow=flow).set(
                                float(synth[f"{flow}:ok"])
                            )
                        if f"{flow}:ms" in synth:
                            _metrics_mod.synthetic_probe_duration.labels(flow=flow).set(
                                float(synth[f"{flow}:ms"]) / 1000.0
                            )
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


def setup_metrics(app: FastAPI) -> None:
    """Instrument the app with Prometheus and expose /metrics endpoint."""
    from prometheus_fastapi_instrumentator import Instrumentator

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
    ).instrument(app)
    instrumentator.expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        dependencies=[Depends(_require_metrics_token)],
    )
    app.middleware("http")(hydrate_custom_metrics)
