"""Unit-тесты для app.services.max_messenger.

Покрывают:
- ``send_message``: успех (200, JSON), 4xx → MaxApiError(status_code), 5xx,
  transport-failure (TimeoutError) → MaxApiError(status_code=None), не-JSON
  ответ (fallback на ``{"_raw": ...}`` без падения отправки).
- ``get_me``: успех, 4xx.
- ``classify_http_error``: transient (5xx/429/timeout/network), permanent
  (4xx кроме 429), unknown (прочее).

httpx-мокается через ``MockTransport`` — без сетевых вызовов.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.max_messenger import (
    MaxApiError,
    classify_http_error,
    close_max_http_client,
    get_me,
    send_message,
)


def _make_client(handler, monkeypatch) -> httpx.AsyncClient:
    """Создать тестовый клиент с MockTransport и подменить singleton."""
    import app.services.max_messenger._client as mod

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(mod, "_MAX_HTTP_CLIENT", client)
    return client


def _ok_handler(body: dict | None = None):
    """Handler, возвращающий 200 OK с JSON-телом."""
    payload = body if body is not None else {"message": {"body": {"mid": "1"}}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


@pytest.fixture(autouse=True)
async def _reset_max_client_after_test():
    """Сбрасываем singleton MAX-клиента после каждого теста (unique MockTransport)."""
    yield
    await close_max_http_client()


@pytest.mark.asyncio
class TestSendMessage:
    async def test_success_returns_json(self, monkeypatch):
        _make_client(_ok_handler({"message": {"mid": "abc"}}), monkeypatch)

        result = await send_message(
            bot_token="t1",
            chat_id="100",
            text="hi",
        )
        assert result == {"message": {"mid": "abc"}}

    async def test_includes_authorization_header(self, monkeypatch):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            captured["chat_id"] = request.url.params.get("chat_id")
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"ok": True})

        _make_client(handler, monkeypatch)

        await send_message(
            bot_token="MYTOKEN",
            chat_id="9876543",
            text="hello",
            attachments=[{"type": "x"}],
        )
        # ВАЖНО: MAX использует голый токен, без "Bearer ".
        assert captured["auth"] == "MYTOKEN"
        assert captured["chat_id"] == "9876543"
        assert captured["body"]["text"] == "hello"
        assert captured["body"]["format"] == "markdown"
        assert captured["body"]["attachments"] == [{"type": "x"}]
        assert captured["body"]["notify"] is True

    async def test_4xx_raises_with_status_code(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"code": "UNAUTHORIZED", "message": "bad token"})

        _make_client(handler, monkeypatch)

        with pytest.raises(MaxApiError) as ei:
            await send_message(bot_token="bad", chat_id="1", text="x")
        assert ei.value.status_code == 401
        assert "401" in str(ei.value)

    async def test_5xx_raises_with_status_code(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "server boom"})

        _make_client(handler, monkeypatch)

        with pytest.raises(MaxApiError) as ei:
            await send_message(bot_token="t", chat_id="1", text="x")
        assert ei.value.status_code == 500

    async def test_transport_error_raises_no_status_code(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("read timeout")

        _make_client(handler, monkeypatch)

        with pytest.raises(MaxApiError) as ei:
            await send_message(bot_token="t", chat_id="1", text="x")
        assert ei.value.status_code is None

    async def test_non_json_response_does_not_crash(self, monkeypatch):
        """Нестандартный ответ (HTML gateway) — не JSON. Не роняет отправку,
        возвращает ``{"_raw": ...}`` чтобы outbox мог mark_sent (стратегия
        «не зацикливать ретраи на парсинге»)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>ok</html>")

        _make_client(handler, monkeypatch)

        result = await send_message(bot_token="t", chat_id="1", text="x")
        assert "_raw" in result


@pytest.mark.asyncio
class TestGetMe:
    async def test_success(self, monkeypatch):
        _make_client(_ok_handler({"user_id": 1, "name": "HelpdeskBot"}), monkeypatch)

        me = await get_me("token")
        assert me == {"user_id": 1, "name": "HelpdeskBot"}

    async def test_4xx_raises(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "invalid token"})

        _make_client(handler, monkeypatch)

        with pytest.raises(MaxApiError) as ei:
            await get_me("bad")
        assert ei.value.status_code == 401


class TestClassifyHttpError:
    def test_5xx_is_transient(self):
        exc = MaxApiError("boom", status_code=500)
        assert classify_http_error(exc) == "transient"

    def test_429_is_transient(self):
        exc = MaxApiError("rate limit", status_code=429)
        assert classify_http_error(exc) == "transient"

    def test_401_is_permanent(self):
        exc = MaxApiError("unauthorized", status_code=401)
        assert classify_http_error(exc) == "permanent"

    def test_404_is_permanent(self):
        exc = MaxApiError("chat not found", status_code=404)
        assert classify_http_error(exc) == "permanent"

    def test_400_is_permanent(self):
        exc = MaxApiError("bad request", status_code=400)
        assert classify_http_error(exc) == "permanent"

    def test_timeout_is_transient(self):
        assert classify_http_error(httpx.TimeoutException("t")) == "transient"

    def test_network_error_is_transient(self):
        assert classify_http_error(httpx.ConnectError("nope")) == "transient"

    def test_unknown_is_unknown(self):
        assert classify_http_error(RuntimeError("weird")) == "unknown"

    def test_max_error_without_status_is_unknown(self):
        # Transport-обёртка (status_code=None) — не должна быть transient как
        # httpx, если только сама обёртка не несёт статуса. На практике мы
        # заворачиваем httpx-исключения, и status_code всегда None при
        # transport-failure → классификация falls through до базовой.
        exc = MaxApiError("transport only")
        assert classify_http_error(exc) == "unknown"
