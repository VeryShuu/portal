"""Unit tests for _hydrate_custom_metrics middleware (app/main.py).

The middleware reads a JSON snapshot from Redis on GET /metrics and populates
Prometheus gauges. Covers:
- Snapshot absent: no error, call_next invoked
- Snapshot present: all known keys hydrated to gauges
- Partial snapshot: missing keys skipped silently
- Non-/metrics path: middleware is transparent (no Redis read)
- Redis raises exception: call_next still invoked (never break /metrics)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch


def _make_request(path: str = "/metrics", redis=None):
    req = MagicMock()
    req.url.path = path
    req.app.state.redis = redis
    return req


async def _noop_next(request):
    return MagicMock()


def patch_db_pool(*, checkedout: int = 0, checkedin: int = 0, pool_size: int = 20, max_overflow: int = 30):
    """Стабает DB pool + settings для /metrics-блока как единый context manager.

    Новый pool-код (middleware/metrics.py) читает engine.pool.checkedout/checkedin
    и get_settings().db_pool_size/db_max_overflow напрямую — это состояние
    API-процесса, не из Redis-snapshot. В unit-тестах стабаем, чтобы не зависеть
    от настоящего engine (он создаётся в module-init, но хрупко на это опираться).

    Использование: ``with patch_db_pool():`` или ``with patch(...), patch_db_pool():``
    """
    from contextlib import ExitStack

    fake_pool = MagicMock()
    fake_pool.checkedout.return_value = checkedout
    fake_pool.checkedin.return_value = checkedin
    fake_engine = MagicMock()
    fake_engine.pool = fake_pool

    fake_settings = MagicMock()
    fake_settings.db_pool_size = pool_size
    fake_settings.db_max_overflow = max_overflow

    stack = ExitStack()
    stack.enter_context(patch("app.core.database.engine", fake_engine))
    stack.enter_context(patch("app.core.config.get_settings", return_value=fake_settings))
    return stack


class TestHydrateCustomMetrics:
    async def _call(self, request):
        from app.middleware.metrics import hydrate_custom_metrics as _hydrate_custom_metrics

        return await _hydrate_custom_metrics(request, _noop_next)

    async def test_non_metrics_path_no_redis_read(self):
        redis = AsyncMock()
        req = _make_request("/api/v1/health", redis=redis)
        await self._call(req)
        redis.get.assert_not_called()

    async def test_no_redis_on_app_state(self):
        req = _make_request("/metrics", redis=None)
        await self._call(req)

    async def test_empty_snapshot_no_error(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        req = _make_request("/metrics", redis=redis)
        await self._call(req)
        redis.get.assert_called_once()

    async def test_full_snapshot_hydrates_gauges(self):
        snap = {
            "audit_queue_depth": 42.0,
            "audit_processing_depth": 3.0,
            "sse_connections": 7.0,
            "active_users_1h": 55.0,
            "photo_storage_bytes": 1_000_000.0,
            "worker_heartbeat_ts": 1_700_000_000.0,
            "kb_articles_total": {"published": 10.0, "draft": 2.0},
            "news_published_total": {"published": 20.0},
            "users_total": {"local": 5.0, "keycloak": 50.0},
        }
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(snap))
        req = _make_request("/metrics", redis=redis)

        gauge_calls: dict[str, list] = {}

        class _FakeGauge:
            def __init__(self, name):
                self._name = name
                gauge_calls.setdefault(name, [])

            def set(self, val):
                gauge_calls[self._name].append(("set", val))

            def labels(self, **kw):
                g = _FakeGauge(f"{self._name}:{kw}")
                return g

        fake_metrics = MagicMock()
        fake_metrics.audit_queue_depth = _FakeGauge("audit_queue_depth")
        fake_metrics.audit_processing_depth = _FakeGauge("audit_processing_depth")
        fake_metrics.sse_connections = _FakeGauge("sse_connections")
        fake_metrics.active_users_1h = _FakeGauge("active_users_1h")
        fake_metrics.photo_storage_bytes = _FakeGauge("photo_storage_bytes")
        fake_metrics.worker_last_heartbeat = _FakeGauge("worker_last_heartbeat")
        fake_metrics.kb_articles_total = _FakeGauge("kb_articles_total")
        fake_metrics.news_published_total = _FakeGauge("news_published_total")
        fake_metrics.users_total = _FakeGauge("users_total")
        # DB pool gauges — читаются напрямую из engine, не из snapshot.
        fake_metrics.db_pool_size = _FakeGauge("db_pool_size")
        fake_metrics.db_pool_limit = _FakeGauge("db_pool_limit")

        with patch("app.middleware.metrics._metrics_mod", fake_metrics), patch_db_pool():
            await self._call(req)

        assert ("set", 42.0) in gauge_calls["audit_queue_depth"]
        assert ("set", 3.0) in gauge_calls["audit_processing_depth"]
        assert ("set", 7.0) in gauge_calls["sse_connections"]
        assert ("set", 55.0) in gauge_calls["active_users_1h"]
        assert ("set", 1_000_000.0) in gauge_calls["photo_storage_bytes"]
        assert ("set", 1_700_000_000.0) in gauge_calls["worker_last_heartbeat"]

    async def test_partial_snapshot_no_error(self):
        snap = {"audit_queue_depth": 5.0}
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(snap))
        req = _make_request("/metrics", redis=redis)

        fake_gauge = MagicMock()
        fake_metrics = MagicMock()
        fake_metrics.audit_queue_depth = fake_gauge
        fake_metrics.audit_processing_depth = MagicMock()
        fake_metrics.sse_connections = MagicMock()
        fake_metrics.active_users_1h = MagicMock()
        fake_metrics.photo_storage_bytes = MagicMock()
        fake_metrics.kb_articles_total = MagicMock()
        fake_metrics.news_published_total = MagicMock()
        fake_metrics.users_total = MagicMock()
        fake_metrics.worker_last_heartbeat = MagicMock()
        # DB pool gauges — вызываются до Redis-read, нужны явно (иначе auto-MagicMock
        # тихо съест вызовы и тест не проверит ничего).
        fake_metrics.db_pool_size = MagicMock()
        fake_metrics.db_pool_limit = MagicMock()

        with patch("app.middleware.metrics._metrics_mod", fake_metrics), patch_db_pool():
            await self._call(req)

        fake_gauge.set.assert_called_once_with(5.0)

    async def test_redis_exception_does_not_break_metrics(self):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("Redis connection lost"))
        req = _make_request("/metrics", redis=redis)
        await self._call(req)

    async def test_malformed_json_does_not_break_metrics(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="not valid json{{{")
        req = _make_request("/metrics", redis=redis)
        await self._call(req)


class TestArqJobsHydration:
    """Гидратация ARQ Counter/Histogram из snapshot (delta-increment)."""

    def _reset_state(self):
        """Сброс module-level state — вызывать явно перед серией вызовов."""
        import app.middleware.metrics as m

        m._arq_job_last.clear()
        m._arq_job_ms_last.clear()

    async def _call(self, snap):
        from app.middleware.metrics import hydrate_custom_metrics as _hydrate

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(snap))
        req = _make_request("/metrics", redis=redis)

        counter_calls: list[tuple] = []
        observe_calls: list[float] = []

        class _FakeCounter:
            def labels(self, **kw):
                counter_calls.append(kw)
                return self

            def inc(self, delta=1.0):
                counter_calls.append(("inc", delta))

        class _FakeHistogram:
            def labels(self, **kw):
                return self

            def observe(self, val):
                observe_calls.append(val)

        fake_metrics = MagicMock()
        for attr in (
            "audit_queue_depth",
            "audit_processing_depth",
            "sse_connections",
            "active_users_1h",
            "photo_storage_bytes",
            "kb_articles_total",
            "news_published_total",
            "users_total",
            "worker_last_heartbeat",
            "db_pool_size",
            "db_pool_limit",
        ):
            setattr(fake_metrics, attr, MagicMock())
        fake_metrics.arq_jobs_total = _FakeCounter()
        fake_metrics.arq_job_duration = _FakeHistogram()

        with patch("app.middleware.metrics._metrics_mod", fake_metrics), patch_db_pool():
            await _hydrate(req, _noop_next)

        return counter_calls, observe_calls

    async def test_arq_jobs_delta_increment(self):
        self._reset_state()
        snap = {
            "arq_jobs": {"send_email:succeeded": 5, "send_email:failed": 1},
            "arq_job_ms": {"send_email:count": 6, "send_email:sum": 6000},
        }
        counter_calls, observe_calls = await self._call(snap)
        assert ("inc", 5.0) in counter_calls
        assert ("inc", 1.0) in counter_calls
        # 6 jobs, 6000 ms total → avg 1.0 s per job
        assert observe_calls == [1.0]

    async def test_arq_jobs_second_snapshot_only_increments_delta(self):
        self._reset_state()
        snap1 = {"arq_jobs": {"job:succeeded": 10}, "arq_job_ms": {}}
        snap2 = {"arq_jobs": {"job:succeeded": 12}, "arq_job_ms": {}}
        await self._call(snap1)
        counter_calls, _ = await self._call(snap2)
        # Дельта = 12 - 10 = 2, не 12
        assert ("inc", 2.0) in counter_calls
        assert ("inc", 12.0) not in counter_calls

    async def test_arq_jobs_no_delta_no_increment(self):
        self._reset_state()
        snap = {"arq_jobs": {"job:succeeded": 5}, "arq_job_ms": {}}
        await self._call(snap)
        # Второй вызов с тем же значением — не должно быть inc
        counter_calls, _ = await self._call(snap)
        assert not any(c == "inc" for c in counter_calls)

    async def test_malformed_field_skipped(self):
        self._reset_state()
        snap = {"arq_jobs": {"no_colon_here": 5, "good:succeeded": 2}, "arq_job_ms": {}}
        # Не должно падать на поле без двоеточия
        counter_calls, _ = await self._call(snap)
        assert ("inc", 2.0) in counter_calls


class TestOutboxHydration:
    """Гидратация outbox-гauges из snapshot."""

    async def _call(self, snap):
        from app.middleware.metrics import hydrate_custom_metrics as _hydrate

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(snap))
        req = _make_request("/metrics", redis=redis)

        gauge_calls: list[tuple] = []

        class _FakeGauge:
            def set(self, val):
                gauge_calls.append(("set", val))

        class _FakeIntegrationGauge:
            def labels(self, integration):
                gauge_calls.append(("labels", integration))
                return self

            def set(self, val):
                gauge_calls.append(("integration", val))

        fake_metrics = MagicMock()
        # Outbox gauges (no labels)
        for attr in (
            "email_outbox_pending",
            "email_outbox_dlq",
            "email_outbox_sending_stale",
            "messenger_outbox_pending",
            "messenger_outbox_dlq",
            "messenger_outbox_sending_stale",
        ):
            setattr(fake_metrics, attr, _FakeGauge())
        fake_metrics.integration_up = _FakeIntegrationGauge()
        # Other gauges used by middleware — safe MagicMock
        for attr in (
            "audit_queue_depth",
            "audit_processing_depth",
            "sse_connections",
            "active_users_1h",
            "photo_storage_bytes",
            "kb_articles_total",
            "news_published_total",
            "users_total",
            "worker_last_heartbeat",
            "db_pool_size",
            "db_pool_limit",
            "arq_jobs_total",
            "arq_job_duration",
        ):
            setattr(fake_metrics, attr, MagicMock())

        with patch("app.middleware.metrics._metrics_mod", fake_metrics), patch_db_pool():
            await _hydrate(req, _noop_next)
        return gauge_calls

    async def test_outbox_gauges_set(self):
        snap = {
            "email_outbox": {"pending": 4, "dlq": 1, "sending_stale": 0},
            "messenger_outbox": {"pending": 2, "dlq": 0, "sending_stale": 0},
        }
        gauge_calls = await self._call(snap)
        assert ("set", 4.0) in gauge_calls  # email pending
        assert ("set", 1.0) in gauge_calls  # email dlq
        assert ("set", 2.0) in gauge_calls  # messenger pending

    async def test_outbox_absent_no_error(self):
        # Snapshot без outbox-ключей — не должно падать
        snap = {"audit_queue_depth": 5}
        await self._call(snap)  # no exception

    async def test_integration_up_set(self):
        snap = {"integrations": {"keycloak": 1, "smtp": 0}}
        gauge_calls = await self._call(snap)
        assert ("labels", "keycloak") in gauge_calls
        assert ("integration", 1.0) in gauge_calls
        assert ("labels", "smtp") in gauge_calls
        assert ("integration", 0.0) in gauge_calls


class TestDBPoolHydration:
    """DB pool gauges читаются напрямую из engine.pool (не из Redis-snapshot).

    Это состояние API-процесса: in_use = checked out, idle = checked in.
    Порог насыщения алерта PortalDBPoolHigh = in_use / (pool_size + max_overflow).
    """

    async def _call(self, *, checkedout=0, checkedin=0, pool_size=20, max_overflow=30):
        from app.middleware.metrics import hydrate_custom_metrics as _hydrate

        # Snapshot пустой — мы тестируем ТОЛЬКО pool-часть (она идёт до Redis).
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        req = _make_request("/metrics", redis=redis)

        gauge_calls: list[tuple] = []

        class _FakeLabeledGauge:
            def labels(self, state):
                gauge_calls.append(("labels", state))
                return self

            def set(self, val):
                gauge_calls.append((("pool_size", None), val))

        class _FakeLimitGauge:
            def set(self, val):
                gauge_calls.append(("pool_limit", val))

        fake_metrics = MagicMock()
        fake_metrics.db_pool_size = _FakeLabeledGauge()
        fake_metrics.db_pool_limit = _FakeLimitGauge()

        with patch("app.middleware.metrics._metrics_mod", fake_metrics), patch_db_pool(
            checkedout=checkedout, checkedin=checkedin,
            pool_size=pool_size, max_overflow=max_overflow,
        ):
            await _hydrate(req, _noop_next)
        return gauge_calls

    async def test_pool_gauges_set(self):
        gauge_calls = await self._call(checkedout=7, checkedin=13, pool_size=20, max_overflow=30)
        # limit = pool_size + max_overflow = 50
        assert ("pool_limit", 50) in gauge_calls
        # in_use / idle values — _FakeLabeledGauge пишет (("pool_size",None), val)
        assert (("pool_size", None), 7) in gauge_calls  # in_use = checkedout
        assert (("pool_size", None), 13) in gauge_calls  # idle = checkedin
        # both states labeled
        assert ("labels", "in_use") in gauge_calls
        assert ("labels", "idle") in gauge_calls

    async def test_pool_limit_uses_current_settings(self):
        # Если admin поднял DB_POOL_SIZE/DB_MAX_OVERFLOW через env, limit меняется.
        gauge_calls = await self._call(pool_size=50, max_overflow=50)
        assert ("pool_limit", 100) in gauge_calls

    async def test_pool_read_error_swallowed(self):
        """engine.pool.checkedout() raises → middleware не падает, /metrics жив."""
        from app.middleware.metrics import hydrate_custom_metrics as _hydrate

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        req = _make_request("/metrics", redis=redis)

        bad_pool = MagicMock()
        bad_pool.checkedout.side_effect = RuntimeError("pool not initialized")
        bad_engine = MagicMock()
        bad_engine.pool = bad_pool

        # call_next должен быть вызван, исключение проглочено.
        next_called = False

        async def _check_next(request):
            nonlocal next_called
            next_called = True
            return MagicMock()

        with patch("app.core.database.engine", bad_engine), \
             patch("app.core.config.get_settings", return_value=MagicMock(db_pool_size=20, db_max_overflow=30)):
            await _hydrate(req, _check_next)

        assert next_called is True
