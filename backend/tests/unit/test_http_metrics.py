"""Unit tests for httpx outbound-request metrics (app/core/http_metrics.py).

Hooks инкрементируют portal_http_client_requests_total{target,method,status}
и наблюдают длительность в portal_http_client_request_duration_seconds{target}.
Проверяем напрямую вызовом хуков на реальных httpx-объектах (без сети).
"""

from __future__ import annotations

from unittest.mock import patch

import httpx

from app.core import http_metrics


def _instrumented_client() -> httpx.AsyncClient:
    client = httpx.AsyncClient()
    return http_metrics.instrument_httpx_client(client, target="keycloak")


class TestInstrumentHttpClient:
    def test_hooks_attached(self):
        client = _instrumented_client()
        assert len(client.event_hooks["request"]) == 1
        assert len(client.event_hooks["response"]) == 1
        # Клиент возвращается тем же объектом (builder-style).
        assert client is not None

    async def test_response_hook_increments_counter_and_histogram(self):
        client = _instrumented_client()
        req_hook = client.event_hooks["request"][0]
        resp_hook = client.event_hooks["response"][0]

        request = httpx.Request("POST", "https://kc.local/token")
        await req_hook(request)
        assert "portal_t0" in request.extensions

        response = httpx.Response(200, request=request)
        with (
            patch.object(http_metrics, "http_client_requests_total") as fake_counter,
            patch.object(http_metrics, "http_client_request_duration") as fake_hist,
        ):
            await resp_hook(response)

        fake_counter.labels.assert_called_once_with(target="keycloak", method="POST", status="200")
        fake_counter.labels.return_value.inc.assert_called_once_with()
        fake_hist.labels.assert_called_once_with(target="keycloak")
        fake_hist.labels.return_value.observe.assert_called_once()

    async def test_response_hook_without_request_hook(self):
        """Response без предшествующего request-hook (t0 нет) — counter инкрементится,
        histogram не наблюдается (нет базы для длительности)."""
        client = _instrumented_client()
        resp_hook = client.event_hooks["response"][0]

        request = httpx.Request("GET", "https://kc.local/x")
        response = httpx.Response(503, request=request)
        with (
            patch.object(http_metrics, "http_client_requests_total") as fake_counter,
            patch.object(http_metrics, "http_client_request_duration") as fake_hist,
        ):
            await resp_hook(response)

        fake_counter.labels.assert_called_once_with(target="keycloak", method="GET", status="503")
        fake_hist.labels.assert_not_called()
