"""Тесты screenshot-service/main.py (аудит тестирования 2026-08-23, P1.4).

Прежде обязательный CI-job «screenshot-service / pytest unit» покрывал только
cookie_utils.py — критические части сервиса (проверка секрета, SSRF-защита,
сетевые ограничения PDF-рендера, readiness, endpoints) не проверялись вовсе,
создавая ложное впечатление защищённости.

Здесь main.py тестируется без реального Chromium: app собирается
production-фабрикой build_app(), on_startup/on_cleanup (реальный браузер)
подменяются стабом app["browser"]. Маршруты, валидация и middleware-логика —
production-код.

Стаб playwright-типов использует утиную типизацию: роутеры дергают только
new_context/new_page/goto/screenshot/pdf/route/is_connected.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

import main as svc


# ─── Stabs браузера (без Chromium) ──────────────────────────────────────────


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = SimpleNamespace(url=url)
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


class _FakeResponse:
    def __init__(self, status: int, payload: object | None = None) -> None:
        self.status = status
        self._payload = payload

    async def json(self) -> object | None:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class _FakePage:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []
        self.route_handlers: list[object] = []
        self.event_handlers: dict[str, list[object]] = {}
        self.url = "about:blank"
        self.missing_selectors: set[str] = set()
        self.page_error_on_home: Exception | None = None
        self.bootstrap_status = 200
        self.bootstrap_payload: object = {
            "user": {
                "id": "00000000-0000-0000-0000-000000000001",
                "email": "probe@example.test",
                "auth_source": "local",
            }
        }
        self.request = SimpleNamespace(post=self.post, get=self.get)

    def on(self, event: str, handler) -> None:
        self.event_handlers.setdefault(event, []).append(handler)

    async def route(self, pattern: str, handler) -> None:
        self.route_handlers.append(handler)

    async def goto(self, url: str, **kwargs) -> None:
        self.events.append(("goto", url))
        self.url = url
        if not url.endswith("/login") and self.page_error_on_home is not None:
            for handler in self.event_handlers.get("pageerror", []):
                handler(self.page_error_on_home)

    async def post(self, url: str, **kwargs) -> _FakeResponse:
        self.events.append(("post", url))
        return _FakeResponse(200)

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        self.events.append(("get", url))
        return _FakeResponse(self.bootstrap_status, self.bootstrap_payload)

    async def wait_for_selector(self, selector: str, **kwargs) -> None:
        self.events.append(("wait_for_selector", selector))
        if selector in self.missing_selectors:
            raise RuntimeError("selector is missing")

    async def wait_for_timeout(self, timeout: float) -> None:
        self.events.append(("wait_for_timeout", timeout))

    async def set_content(self, html: str, **kwargs) -> None:
        self.events.append(("set_content", len(html)))

    async def screenshot(self, **kwargs) -> bytes:
        return b"FAKE-PNG-BYTES"

    async def pdf(self, **kwargs) -> bytes:
        return b"%PDF-1.4 fake"


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self.page = page

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        pass

    async def cookies(self) -> list[dict]:
        return []

    async def add_cookies(self, cookies: list[dict]) -> None:
        pass


class _FakeBrowser:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.page = _FakePage()

    def is_connected(self) -> bool:
        return self._connected

    async def new_context(self, **kwargs) -> _FakeContext:
        return _FakeContext(self.page)


def _make_app(browser=None) -> object:
    """Production build_app() без запуска Chromium (on_startup/on_cleanup сняты)."""
    app = svc.build_app()
    app.on_startup[:] = []
    app.on_cleanup[:] = []
    if browser is not None:
        app["browser"] = browser
    return app


@pytest.fixture
def secret(monkeypatch) -> str:
    value = "test-secret-123"
    monkeypatch.setattr(svc, "_SERVICE_SECRET", value)
    return value


@pytest.fixture
def allowed(monkeypatch) -> list[str]:
    origins = ["https://portal.mage.ru"]
    monkeypatch.setattr(svc, "_ALLOWED_ORIGINS", origins)
    return origins


@pytest.fixture
async def client(secret, allowed):
    async with TestClient(TestServer(_make_app(browser=_FakeBrowser()))) as c:
        yield c


# ─── _validate_screenshot_url: SSRF-защита (unit) ───────────────────────────


class TestValidateScreenshotUrl:
    def test_internal_ipv4_blocked(self):
        for host in (
            "192.168.1.1",
            "10.0.0.5",
            "172.16.31.4",
            "127.0.0.1",
            "169.254.1.1",
        ):
            err = svc._validate_screenshot_url(f"http://{host}/x")
            assert err == "url resolves to an internal address", host

    def test_internal_ipv6_blocked(self):
        assert svc._validate_screenshot_url("http://[::1]/x") == (
            "url resolves to an internal address"
        )

    def test_non_http_scheme_blocked(self):
        assert svc._validate_screenshot_url("ftp://portal.mage.ru/x") == (
            "url scheme must be http or https"
        )
        assert svc._validate_screenshot_url("file:///etc/passwd") == (
            "url scheme must be http or https"
        )

    def test_no_allowlist_disables_endpoint(self, secret, monkeypatch):
        monkeypatch.setattr(svc, "_ALLOWED_ORIGINS", [])
        err = svc._validate_screenshot_url("https://portal.mage.ru/")
        assert err == (
            "SCREENSHOT_ALLOWED_ORIGINS is not configured — screenshot endpoint is disabled"
        )

    def test_foreign_origin_blocked(self, secret, allowed):
        assert svc._validate_screenshot_url("https://evil.example.com/") == (
            "url origin is not in the allowed list"
        )

    def test_allowed_origin_passes(self, secret, allowed):
        assert svc._validate_screenshot_url("https://portal.mage.ru/news") is None

    def test_hostname_required(self, secret, allowed):
        assert svc._validate_screenshot_url("https:///path") == "url must have a host"


# ─── _block_all_network: сетевая изоляция PDF-рендера (unit) ────────────────


class TestBlockAllNetwork:
    async def test_data_uri_allowed(self):
        route = _FakeRoute("data:image/png;base64,xxx")
        await svc._block_all_network(route)
        assert route.continued and not route.aborted

    async def test_blob_uri_allowed(self):
        route = _FakeRoute("blob:https://portal.mage.ru/uuid")
        await svc._block_all_network(route)
        assert route.continued and not route.aborted

    async def test_http_blocked(self):
        route = _FakeRoute("http://evil.example.com/pixel.png")
        await svc._block_all_network(route)
        assert route.aborted and not route.continued

    async def test_https_blocked(self):
        route = _FakeRoute("https://portal.mage.com/logo.svg")
        await svc._block_all_network(route)
        assert route.aborted and not route.continued


# ─── /screenshot: секрет + валидации + happy path (endpoint) ────────────────


class TestScreenshotEndpoint:
    async def test_missing_secret_header_401(self, client):
        resp = await client.get(
            "/screenshot", params={"url": "https://portal.mage.ru/"}
        )
        assert resp.status == 401

    async def test_wrong_secret_header_401(self, client):
        resp = await client.get(
            "/screenshot",
            params={"url": "https://portal.mage.ru/"},
            headers={"X-Screenshot-Secret": "wrong"},
        )
        assert resp.status == 401

    async def test_unconfigured_secret_503(self, allowed, monkeypatch):
        monkeypatch.setattr(svc, "_SERVICE_SECRET", "")
        async with TestClient(TestServer(_make_app(browser=_FakeBrowser()))) as c:
            resp = await c.get(
                "/screenshot",
                params={"url": "https://portal.mage.ru/"},
                headers={"X-Screenshot-Secret": "any"},
            )
        assert resp.status == 503

    async def test_ssrf_internal_ip_400(self, client):
        resp = await client.get(
            "/screenshot",
            params={"url": "http://192.168.0.1/admin"},
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400
        assert "internal address" in (await resp.json())["error"]

    async def test_ssrf_foreign_origin_400(self, client):
        resp = await client.get(
            "/screenshot",
            params={"url": "https://evil.example.com/"},
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400
        assert "not in the allowed list" in (await resp.json())["error"]

    async def test_url_required_400(self, client):
        resp = await client.get(
            "/screenshot",
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400

    async def test_width_height_validated(self, client):
        base = {"url": "https://portal.mage.ru/"}
        headers = {"X-Screenshot-Secret": "test-secret-123"}
        resp = await client.get(
            "/screenshot", params={**base, "width": "99999"}, headers=headers
        )
        assert resp.status == 400
        resp = await client.get(
            "/screenshot", params={**base, "width": "abc"}, headers=headers
        )
        assert resp.status == 400

    async def test_happy_path_returns_png(self, client):
        resp = await client.get(
            "/screenshot",
            params={
                "url": "https://portal.mage.ru/news",
                "width": "800",
                "height": "600",
            },
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 200
        assert resp.content_type == "image/png"
        assert await resp.read() == b"FAKE-PNG-BYTES"


# ─── /pdf ───────────────────────────────────────────────────────────────────


class TestPdfEndpoint:
    async def test_requires_secret(self, client):
        resp = await client.post("/pdf", json={"html": "<b>x</b>"})
        assert resp.status == 401

    async def test_empty_html_400(self, client):
        resp = await client.post(
            "/pdf",
            json={"html": ""},
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400

    async def test_happy_path_pdf_and_network_isolation(self, secret, allowed):
        browser = _FakeBrowser()
        async with TestClient(TestServer(_make_app(browser=browser))) as client:
            resp = await client.post(
                "/pdf",
                json={
                    "html": "<h1>Отчёт</h1><img src='http://evil.example.com/x.png'>"
                },
                headers={"X-Screenshot-Secret": "test-secret-123"},
            )
            assert resp.status == 200
            assert resp.content_type == "application/pdf"
            assert (await resp.read()).startswith(b"%PDF")

            # сетевая изоляция: на страницу обязан быть навешан блокирующий
            # route-handler ДО рендера контента
            page = browser.page
            assert page.route_handlers, (
                "PDF-рендер без route-изоляции — SSRF через контент"
            )
            assert page.events and page.events[0][0] == "set_content"


# ─── /health и /ready ───────────────────────────────────────────────────────


class TestHealthAndReady:
    async def test_ready_503_without_browser(self, secret, allowed):
        async with TestClient(TestServer(_make_app(browser=None))) as c:
            resp = await c.get("/ready")
            assert resp.status == 503
            assert (await resp.json())["reason"] == "browser_not_initialized"

    async def test_ready_503_disconnected_browser(self, secret, allowed):
        async with TestClient(
            TestServer(_make_app(browser=_FakeBrowser(connected=False)))
        ) as c:
            resp = await c.get("/ready")
            assert resp.status == 503
            assert (await resp.json())["reason"] == "browser_disconnected"

    async def test_ready_200_connected(self, client):
        resp = await client.get("/ready")
        assert resp.status == 200
        assert (await resp.json())["status"] == "ready"

    async def test_health_reports_configuration(self, secret, allowed):
        async with TestClient(TestServer(_make_app(browser=_FakeBrowser()))) as c:
            ok = await c.get("/health")
            assert ok.status == 200
            assert (await ok.json())["configured"] is True

        monkeypatch_configured = ("", [])
        svc._SERVICE_SECRET, svc._ALLOWED_ORIGINS = monkeypatch_configured
        try:
            async with TestClient(TestServer(_make_app(browser=_FakeBrowser()))) as c:
                bad = await c.get("/health")
                assert bad.status == 200
                assert (await bad.json())["configured"] is False
        finally:
            svc._SERVICE_SECRET, svc._ALLOWED_ORIGINS = (
                "test-secret-123",
                ["https://portal.mage.ru"],
            )


# ─── /probe ─────────────────────────────────────────────────────────────────


async def _run_configured_probe(monkeypatch, browser: _FakeBrowser) -> tuple[dict, str]:
    monkeypatch.setattr(svc, "_SERVICE_SECRET", "test-secret-123")
    monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
    monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
    async with TestClient(TestServer(_make_app(browser=browser))) as client:
        response = await client.post(
            "/probe",
            json={
                "flow": "login_and_load",
                "portal_base_url": "https://portal.example.test",
            },
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        body = await response.json()
        metrics = await (await client.get("/metrics")).text()
    return body, metrics


class TestProbeEndpoint:
    async def test_requires_secret(self, client):
        resp = await client.post("/probe", json={"flow": "login_and_load"})
        assert resp.status == 401

    async def test_unknown_flow_400(self, client):
        resp = await client.post(
            "/probe",
            json={"flow": "rm -rf"},
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400

    async def test_unconfigured_probe_reports_configured_false(
        self, client, monkeypatch
    ):
        monkeypatch.delenv("PROBE_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("PROBE_ADMIN_PASSWORD", raising=False)
        resp = await client.post(
            "/probe",
            json={"flow": "login_and_load"},
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is False
        assert body["configured"] is False

    async def test_invalid_json_400(self, client):
        resp = await client.post(
            "/probe",
            data="not-json",
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert resp.status == 400

    async def test_success_requires_home_marker_and_matching_bootstrap(self, monkeypatch):
        browser = _FakeBrowser()
        body, metrics = await _run_configured_probe(monkeypatch, browser)

        assert body["ok"] is True
        assert ("wait_for_selector", '[data-monitoring-ready="home"]') in (
            browser.page.events
        )
        assert ("get", "http://frontend:80/api/v1/bootstrap") in browser.page.events
        assert _metric_value(metrics, "portal_synthetic_probe_up") == 1

    async def test_pageerror_is_safe_fresh_failure(self, monkeypatch, caplog):
        browser = _FakeBrowser()
        browser.page.page_error_on_home = RuntimeError("sensitive-pageerror-canary")
        body, metrics = await _run_configured_probe(monkeypatch, browser)

        assert body["ok"] is False
        assert body["step_failed"] == "page_error"
        assert "sensitive-pageerror-canary" not in str(body)
        assert "sensitive-pageerror-canary" not in caplog.text
        assert _metric_value(metrics, "portal_synthetic_probe_result_available") == 1
        assert _metric_value(metrics, "portal_synthetic_probe_up") == 0

    async def test_missing_authorized_content_is_fresh_failure(self, monkeypatch):
        browser = _FakeBrowser()
        browser.page.missing_selectors.add('[data-monitoring-ready="home"]')
        body, metrics = await _run_configured_probe(monkeypatch, browser)

        assert body["ok"] is False
        assert body["step_failed"] == "authorized_content_missing"
        assert _metric_value(metrics, "portal_synthetic_probe_up") == 0

    @pytest.mark.parametrize("status", [401, 503], ids=["unauthorized", "unavailable"])
    async def test_bootstrap_http_failure_is_classified(
        self, monkeypatch, status
    ):
        browser = _FakeBrowser()
        browser.page.bootstrap_status = status
        body, metrics = await _run_configured_probe(monkeypatch, browser)

        assert body["ok"] is False
        assert body["step_failed"] == f"bootstrap_status_{status}"
        assert _metric_value(metrics, "portal_synthetic_probe_up") == 0

    @pytest.mark.parametrize(
        "payload",
        [
            ValueError("sensitive-invalid-json-canary"),
            {},
            {"user": {"email": "probe@example.test", "auth_source": "local"}},
            {
                "user": {
                    "id": "user-id",
                    "email": "other@example.test",
                    "auth_source": "local",
                }
            },
            {
                "user": {
                    "id": "user-id",
                    "email": "probe@example.test",
                    "auth_source": "keycloak",
                }
            },
        ],
        ids=["invalid-json", "missing-user", "missing-id", "wrong-email", "not-local"],
    )
    async def test_invalid_bootstrap_identity_is_safe_failure(
        self, monkeypatch, payload
    ):
        browser = _FakeBrowser()
        browser.page.bootstrap_payload = payload
        body, metrics = await _run_configured_probe(monkeypatch, browser)

        assert body["ok"] is False
        assert body["step_failed"] == "bootstrap_invalid"
        assert "other@example.test" not in str(body)
        assert "sensitive-invalid-json-canary" not in str(body)
        assert _metric_value(metrics, "portal_synthetic_probe_up") == 0


def _metric_value(text: str, name: str) -> float | None:
    prefix = f'{name}{{flow="login_and_load"}} '
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line[len(prefix) :])
    return None


class TestProbeMetrics:
    async def test_disabled_is_explicit_without_result(self, client, monkeypatch):
        monkeypatch.delenv("PROBE_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("PROBE_ADMIN_PASSWORD", raising=False)
        response = await client.get("/metrics")
        text = await response.text()
        assert response.status == 200
        assert _metric_value(text, "portal_synthetic_probe_expected") == 0
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 0
        assert _metric_value(text, "portal_synthetic_probe_up") is None

    async def test_successful_endpoint_exports_fresh_result(self, client, monkeypatch):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        response = await client.post(
            "/probe",
            json={
                "flow": "login_and_load",
                "portal_base_url": "https://portal.example.test",
            },
            headers={"X-Screenshot-Secret": "test-secret-123"},
        )
        assert response.status == 200
        assert (await response.json())["ok"] is True

        metrics_response = await client.get("/metrics")
        text = await metrics_response.text()
        assert _metric_value(text, "portal_synthetic_probe_expected") == 1
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 1
        assert _metric_value(text, "portal_synthetic_probe_up") == 1
        assert (
            _metric_value(text, "portal_synthetic_probe_duration_seconds") is not None
        )
        assert (
            _metric_value(
                text,
                "portal_synthetic_probe_last_attempt_timestamp_seconds",
            )
            is not None
        )
        assert (
            _metric_value(
                text,
                "portal_synthetic_probe_last_completed_timestamp_seconds",
            )
            is not None
        )

    def test_attempt_without_completion_is_stale(self, monkeypatch):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        probe_metrics = svc._ProbeMetrics()
        probe_metrics.mark_attempt()
        text = probe_metrics.render().decode()
        assert _metric_value(text, "portal_synthetic_probe_expected") == 1
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 0
        assert (
            _metric_value(
                text,
                "portal_synthetic_probe_last_attempt_timestamp_seconds",
            )
            is not None
        )
        assert (
            _metric_value(
                text,
                "portal_synthetic_probe_last_completed_timestamp_seconds",
            )
            is None
        )

    def test_expired_result_is_removed(self, monkeypatch):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        probe_metrics = svc._ProbeMetrics()
        probe_metrics.completed_at = 1.0
        probe_metrics.last_ok = True
        probe_metrics.last_duration_seconds = 2.5
        probe_metrics.last_completed.labels("login_and_load").set(1.0)
        monkeypatch.setattr(svc.time, "time", lambda: 1000.0)
        text = probe_metrics.render().decode()
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 0
        assert _metric_value(text, "portal_synthetic_probe_up") is None
        assert _metric_value(text, "portal_synthetic_probe_duration_seconds") is None

    def test_new_process_does_not_reuse_old_green_result(self, monkeypatch):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        old = svc._ProbeMetrics()
        old.mark_completed(ok=True, elapsed_ms=2500)
        assert _metric_value(old.render().decode(), "portal_synthetic_probe_up") == 1

        restarted = svc._ProbeMetrics()
        text = restarted.render().decode()
        assert _metric_value(text, "portal_synthetic_probe_expected") == 1
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 0
        assert _metric_value(text, "portal_synthetic_probe_up") is None

    def test_failed_completion_is_fresh_down(self, monkeypatch):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        probe_metrics = svc._ProbeMetrics()
        probe_metrics.mark_attempt()
        probe_metrics.mark_completed(ok=False, elapsed_ms=12000)
        text = probe_metrics.render().decode()
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 1
        assert _metric_value(text, "portal_synthetic_probe_up") == 0
        assert _metric_value(text, "portal_synthetic_probe_duration_seconds") == 12

    @pytest.mark.parametrize("missing", ["email", "password"])
    def test_both_credentials_are_required(self, monkeypatch, missing):
        monkeypatch.setenv("PROBE_ADMIN_EMAIL", "probe@example.test")
        monkeypatch.setenv("PROBE_ADMIN_PASSWORD", "secret")
        monkeypatch.delenv(
            "PROBE_ADMIN_EMAIL" if missing == "email" else "PROBE_ADMIN_PASSWORD"
        )
        text = svc._ProbeMetrics().render().decode()
        assert _metric_value(text, "portal_synthetic_probe_expected") == 0
        assert _metric_value(text, "portal_synthetic_probe_result_available") == 0
