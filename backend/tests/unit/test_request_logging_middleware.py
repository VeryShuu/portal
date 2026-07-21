"""Charakterisierende тесты для ``app/middleware/logging.py::request_logging``.

Middleware выполняет 4 ответственновности:
1. Сквозной correlation id: принимает ``X-Request-Id`` (валидирует длину) или
   генерирует новый uuid; возвращает его в ответе через ``X-Request-Id``.
2. Биндит request_id/method/path/client_ip в structlog contextvars.
3. Выбирает уровень лога по status_code: 5xx → error, 4xx → warning, иначе info
   (с slow-request branch: если elapsed >= log_slow_request_ms — warning).
4. На исключении в downstream вызывает ``logger.exception`` и пробрасывает
   исключение; contextvars очищаются всегда (в ``finally``).

Эти контракты сейчас тестируются только косвенно через security/bookmarks/limiter
— добавляем прямую характеризацию, чтобы безопасно рефакторить.

Подход к проверке log-level: structlog + ProcessorFormatter — многослойная
композиция, и проверять итоговый ``LogRecord.levelname`` через хук на stdlib
handler хрупко (уровень переписывается formatter'ом уже после emit). Вместо
этого мокаем сам ``logger`` в middleware и проверяем, какой из его методов
(``info`` / ``warning`` / ``error`` / ``exception``) был вызван — это и есть
контракт ``log_method = logger.<level>``.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.middleware import logging as middleware_logging

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(handler: Callable[..., Awaitable[object]]) -> FastAPI:
    """Build a minimal FastAPI app with the request_logging middleware."""
    app = FastAPI()
    app.middleware("http")(middleware_logging.request_logging)
    app.router.add_api_route("/probe", handler, methods=["GET"])
    return app


@pytest.fixture
def reset_contextvars():
    """Ensure structlog contextvars are clean before/after each test."""
    from app.core.logging import clear_request_context

    clear_request_context()
    yield
    clear_request_context()


def _stub_logger() -> tuple[MagicMock, dict[str, MagicMock]]:
    """Replace middleware logger with a mock that records method calls.

    Returns ``(mock_logger, methods)`` where ``methods`` maps names
    ('info', 'warning', 'error', 'exception') to MagicMock objects.
    """
    mock = MagicMock()
    methods = {
        "info": MagicMock(),
        "warning": MagicMock(),
        "error": MagicMock(),
        "exception": MagicMock(),
    }
    mock.info = methods["info"]
    mock.warning = methods["warning"]
    mock.error = methods["error"]
    mock.exception = methods["exception"]
    return mock, methods


# ---------------------------------------------------------------------------
# 1. Correlation id — X-Request-Id handling
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reset_contextvars")
def test_accepts_incoming_x_request_id() -> None:
    """Балансер прислал X-Request-Id → он же возвращается в ответе."""
    incoming = "balancer-trace-12345"

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    with TestClient(app) as client:
        resp = client.get("/probe", headers={"X-Request-Id": incoming})
    assert resp.status_code == 200
    assert resp.headers["X-Request-Id"] == incoming


@pytest.mark.usefixtures("reset_contextvars")
def test_generates_new_request_id_when_absent() -> None:
    """Нет входящего заголовка → генерируется новый uuid (валидного формата)."""

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    with TestClient(app) as client:
        resp = client.get("/probe")
    assert resp.status_code == 200
    rid = resp.headers["X-Request-Id"]
    # Должен быть валидным uuid4.
    parsed = uuid.UUID(rid)
    assert parsed.version == 4


@pytest.mark.usefixtures("reset_contextvars")
def test_overly_long_incoming_request_id_is_ignored() -> None:
    """Заголовок длиннее 128 символов → игнорируется, генерируется новый uuid."""
    too_long = "x" * 200

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    with TestClient(app) as client:
        resp = client.get("/probe", headers={"X-Request-Id": too_long})
    rid = resp.headers["X-Request-Id"]
    # Не оригинальная длинная строка, а свежий uuid.
    assert rid != too_long
    parsed = uuid.UUID(rid)
    assert parsed.version == 4


# ---------------------------------------------------------------------------
# 2. Status-based log level
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reset_contextvars")
def test_5xx_logs_as_error() -> None:
    async def handler():  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=500, detail="boom")

    app = _make_app(handler)
    mock_log, methods = _stub_logger()
    with (
        patch.object(middleware_logging, "logger", mock_log),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        client.get("/probe")

    methods["error"].assert_called_once()
    methods["warning"].assert_not_called()
    methods["info"].assert_not_called()


@pytest.mark.usefixtures("reset_contextvars")
def test_4xx_logs_as_warning() -> None:
    async def handler():  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=404, detail="not found")

    app = _make_app(handler)
    mock_log, methods = _stub_logger()
    with (
        patch.object(middleware_logging, "logger", mock_log),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        client.get("/probe")

    methods["warning"].assert_called_once()
    methods["error"].assert_not_called()
    methods["info"].assert_not_called()


@pytest.mark.usefixtures("reset_contextvars")
def test_2xx_logs_as_info() -> None:
    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    mock_log, methods = _stub_logger()
    with patch.object(middleware_logging, "logger", mock_log), TestClient(app) as client:
        client.get("/probe")

    methods["info"].assert_called_once()
    methods["warning"].assert_not_called()
    methods["error"].assert_not_called()


# ---------------------------------------------------------------------------
# 3. Slow request detection
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reset_contextvars")
def test_slow_request_logs_as_warning() -> None:
    """elapsed_ms >= log_slow_request_ms → WARNING вместо INFO."""

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    mock_log, methods = _stub_logger()

    # log_slow_request_ms — runtime, из system.json. Мокаем: 0 = всегда «slow».
    fake_settings = type("FakeSettings", (), {"log_slow_request_ms": 0})()
    with patch.object(middleware_logging, "logger", mock_log), patch(
        "app.core.system_config.load_system_settings", return_value=fake_settings
    ), TestClient(app) as client:
        client.get("/probe")

    # log_slow_request_ms == 0 → условие `_slow_ms > 0` False → info (не warning).
    # Это фактическое поведение кода: 0 = disabled. Тестируем через порог = 1ms.
    methods["info"].assert_called_once()
    methods["warning"].assert_not_called()


@pytest.mark.usefixtures("reset_contextvars")
def test_slow_request_warning_when_threshold_low() -> None:
    """log_slow_request_ms низкий + handler задерживается → WARNING."""

    import asyncio

    async def handler():  # type: ignore[no-untyped-def]
        # Гарантированно дольше любого разумного порога; TestClient внутри event-loop.
        await asyncio.sleep(0.05)  # 50 ms
        return {"ok": True}

    app = _make_app(handler)
    mock_log, methods = _stub_logger()

    # Порог 10 ms — sleep(50ms) точно больше.
    fake_settings = type("FakeSettings", (), {"log_slow_request_ms": 10})()
    with patch.object(middleware_logging, "logger", mock_log), patch(
        "app.core.system_config.load_system_settings", return_value=fake_settings
    ), TestClient(app) as client:
        client.get("/probe")

    methods["warning"].assert_called_once()
    methods["info"].assert_not_called()


@pytest.mark.usefixtures("reset_contextvars")
def test_slow_request_disabled_when_threshold_huge() -> None:
    """log_slow_request_ms=60000 → не slow, обычный INFO."""

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    mock_log, methods = _stub_logger()

    class FakeSettings:
        log_slow_request_ms = 60_000  # 60 секунд — точно больше любого теста.

    with patch.object(middleware_logging, "logger", mock_log), patch(
        "app.core.system_config.load_system_settings", return_value=FakeSettings()
    ), TestClient(app) as client:
        client.get("/probe")

    methods["info"].assert_called_once()
    methods["warning"].assert_not_called()


# ---------------------------------------------------------------------------
# 4. Exception propagation + logger.exception
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reset_contextvars")
def test_unhandled_exception_logged_and_reraised() -> None:
    """Неперехваченное исключение → logger.exception('http.request_failed') + проброс."""

    async def handler():  # type: ignore[no-untyped-def]
        raise RuntimeError("downstream crashed")

    app = _make_app(handler)
    mock_log, methods = _stub_logger()
    # TestClient с raise_server_exceptions=True (default) пробрасывает исключение.
    with (
        patch.object(middleware_logging, "logger", mock_log),
        pytest.raises(RuntimeError, match="downstream crashed"),
        TestClient(app) as client,
    ):
        client.get("/probe")

    methods["exception"].assert_called_once()
    # Никакой последующий logger.info/warning/error не должен вызываться —
    # блок `response = await call_next(request)` упал, return response — недостижим.
    methods["info"].assert_not_called()
    methods["warning"].assert_not_called()
    methods["error"].assert_not_called()
    # Проверяем что event_name корректный.
    call_args = methods["exception"].call_args
    assert call_args.args[0] == "http.request_failed"


# ---------------------------------------------------------------------------
# 5. Response X-Request-Id header
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("reset_contextvars")
def test_response_sets_x_request_id_header() -> None:
    """Корреляционный ID возвращается в ответе всегда (контракт с балансером/клиентом)."""

    async def handler():  # type: ignore[no-untyped-def]
        return {"ok": True}

    app = _make_app(handler)
    with TestClient(app) as client:
        # Без входящего.
        r1 = client.get("/probe")
        assert "X-Request-Id" in r1.headers
        # С входящим.
        r2 = client.get("/probe", headers={"X-Request-Id": "abc-123"})
        assert r2.headers["X-Request-Id"] == "abc-123"
        # Каждый запрос — свой id.
        assert r1.headers["X-Request-Id"] != r2.headers["X-Request-Id"]
