"""Unit tests for SSE-exclusion in the latency histogram (middleware/metrics.py).

``_latency_excluding_sse`` оборачивает пакетную ``latency()``: для SSE-хендлера
уведомлений observe пропускается (длительность стрима = время жизни соединения,
а не латентность), для остальных хендлеров — делегируется базовой метрике.
Базовую метрику мокаем (в стиле test_http_metrics.py): реальная Histogram в
глобальной REGISTRY хрупка при параллельном прогоне (duplicate timeseries).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from prometheus_fastapi_instrumentator.metrics import Info
from starlette.requests import Request

from app.middleware.metrics import _latency_excluding_sse

_BUCKETS = (0.1, 1.0, 10.0, 60.0)


def _info(handler: str, duration: float = 42.0) -> Info:
    return Info(
        request=Request(scope={"type": "http", "method": "GET", "path": handler}),
        response=None,
        method="GET",
        modified_handler=handler,
        modified_status="2xx",
        modified_duration=duration,
    )


class TestLatencyExcludingSse:
    def test_sse_stream_handler_not_observed(self) -> None:
        """Долгоживущий SSE-стрим не попадает в latency-гистограмму."""
        fake_base = MagicMock()
        with patch("prometheus_fastapi_instrumentator.metrics.latency", return_value=fake_base):
            metric = _latency_excluding_sse(buckets=_BUCKETS)

        metric(_info("/api/v1/notifications/stream", duration=60.0))
        fake_base.assert_not_called()

    def test_regular_handler_observed(self) -> None:
        """Обычный хендлер делегируется базовой latency-метрике как есть."""
        fake_base = MagicMock()
        with patch("prometheus_fastapi_instrumentator.metrics.latency", return_value=fake_base):
            metric = _latency_excluding_sse(buckets=_BUCKETS)

        info = _info("/api/v1/files/folders/{folder_id}")
        metric(info)
        fake_base.assert_called_once_with(info)

    def test_base_metric_none_does_not_raise(self) -> None:
        """Пакетная latency() может вернуть None (duplicate registry при
        повторной регистрации) — обёртка молча пропускает, не падая."""
        with patch("prometheus_fastapi_instrumentator.metrics.latency", return_value=None):
            metric = _latency_excluding_sse(buckets=_BUCKETS)

        metric(_info("/api/v1/anything"))  # не raises
