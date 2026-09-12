"""Мониторинг исходящих HTTP-запросов (httpx) к внешним сервисам.

Латентность Keycloak/Nextcloud/Matrix/MAX ранее была невидима: единственный
датчик — бинарный ``portal_integration_up``. Хуки ниже дают счётчик и
гистограмму по целевым сервисам — видно, что логин медленный ИЗ-ЗА Keycloak,
а не из-за портала.

Использование (каждое место создания httpx.AsyncClient):

    from app.core.http_metrics import instrument_httpx_client
    client = instrument_httpx_client(httpx.AsyncClient(...), target="keycloak")

Лейбл ``target`` — фиксированный набор значений (keycloak/nextcloud/matrix/max),
низкая кардинальность.

NB: считаются только запросы, ДОШЕДШИЕ до ответа — на connect-error/timeout
response-hook не вызывается (availability-часть закрыта ``portal_integration_up``
probe). Метрики живут в процессе, где создан клиент: для воркерских клиентов
(matrix/max при рассылке outbox) значения не скрейпятся — см. docs/monitoring.md.
"""

from __future__ import annotations

import time

import httpx
from prometheus_client import Counter, Histogram

http_client_requests_total = Counter(
    "portal_http_client_requests_total",
    "Outbound HTTP requests via httpx by target service.",
    labelnames=("target", "method", "status"),
)

http_client_request_duration = Histogram(
    "portal_http_client_request_duration_seconds",
    "Outbound HTTP request latency (httpx) by target service.",
    labelnames=("target",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def instrument_httpx_client(client: httpx.AsyncClient, *, target: str) -> httpx.AsyncClient:
    """Attach request/response event hooks with portal_http_client_* metrics."""

    async def _on_request(request: httpx.Request) -> None:
        request.extensions["portal_t0"] = time.perf_counter()

    async def _on_response(response: httpx.Response) -> None:
        http_client_requests_total.labels(
            target=target,
            method=response.request.method,
            status=str(response.status_code),
        ).inc()
        t0 = response.request.extensions.get("portal_t0")
        if t0 is not None:
            http_client_request_duration.labels(target=target).observe(time.perf_counter() - t0)

    client.event_hooks["request"].append(_on_request)
    client.event_hooks["response"].append(_on_response)
    return client
