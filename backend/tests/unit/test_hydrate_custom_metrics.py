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

import pytest

pytestmark = pytest.mark.asyncio


def _make_request(path: str = "/metrics", redis=None):
    req = MagicMock()
    req.url.path = path
    req.app.state.redis = redis
    return req


async def _noop_next(request):
    return MagicMock()


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
        fake_metrics.kb_articles_total = _FakeGauge("kb_articles_total")
        fake_metrics.news_published_total = _FakeGauge("news_published_total")
        fake_metrics.users_total = _FakeGauge("users_total")

        with patch("app.middleware.metrics._metrics_mod", fake_metrics):
            await self._call(req)

        assert ("set", 42.0) in gauge_calls["audit_queue_depth"]
        assert ("set", 3.0) in gauge_calls["audit_processing_depth"]
        assert ("set", 7.0) in gauge_calls["sse_connections"]
        assert ("set", 55.0) in gauge_calls["active_users_1h"]
        assert ("set", 1_000_000.0) in gauge_calls["photo_storage_bytes"]

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

        with patch("app.middleware.metrics._metrics_mod", fake_metrics):
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
