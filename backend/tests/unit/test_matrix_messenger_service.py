"""Unit-тесты для app.services.matrix_messenger.

Покрывают:
- ``matrix_id_for_user``: конвенция email → MXID (lowercase, «собака»→двоеточие).
- ``whoami`` / ``send_message`` / ``create_dm`` / ``get_direct_rooms`` /
  ``set_direct_room``: успех, 4xx/5xx → MatrixApiError(status, errcode),
  transport-failure → без статуса, не-JSON 2xx — не роняет отправку.
- ``send_message``: Bearer-заголовок, PUT + txnId в пути, formatted_body
  только при наличии, room_id экранируется.
- ``get_direct_rooms``: 404 M_NOT_FOUND → {} (нет account data — норма),
  мусорные значения отфильтровываются.
- ``classify_http_error``: transient (429/5xx/timeout/network), permanent
  (401/403/400), unknown (прочее).

httpx-мокается через ``MockTransport`` — без сетевых вызовов.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.matrix_messenger import (
    MatrixApiError,
    classify_http_error,
    close_matrix_http_client,
    create_dm,
    get_direct_rooms,
    matrix_id_for_user,
    send_message,
    set_direct_room,
    whoami,
)
from app.services.matrix_messenger.dm import DmResolver

BASE = "https://matrix.mage.ru"
TOKEN = "mct_testtoken"


def _make_client(handler, monkeypatch) -> httpx.AsyncClient:
    """Создать тестовый клиент с MockTransport и подменить singleton."""
    import app.services.matrix_messenger._client as mod

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(mod, "_MATRIX_HTTP_CLIENT", client)
    return client


@pytest.fixture(autouse=True)
async def _reset_matrix_client_after_test():
    """Сбрасываем singleton Matrix-клиента после каждого теста."""
    yield
    await close_matrix_http_client()


# ── matrix_id_for_user ───────────────────────────────────────────────────


class TestMatrixIdForUser:
    def test_convention(self):
        assert (
            matrix_id_for_user("borzihin.vs@mage.ru", "matrix.mage.ru")
            == "@borzihin.vs:matrix.mage.ru"
        )

    def test_lowercase(self):
        """Localpart MXID чувствителен к регистру — всегда lowercase."""
        assert (
            matrix_id_for_user("Ivanov.II@mage.ru", "matrix.mage.ru") == "@ivanov.ii:matrix.mage.ru"
        )

    def test_plus_addressing_kept_verbatim(self):
        """plus-addressing не нормализуем — это уже другой аккаунт Matrix."""
        assert (
            matrix_id_for_user("ivanov+news@mage.ru", "matrix.mage.ru")
            == "@ivanov+news:matrix.mage.ru"
        )


# ── whoami ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWhoami:
    async def test_success(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(200, json={"user_id": "@portal-bot:matrix.mage.ru"}),
            monkeypatch,
        )
        me = await whoami(homeserver_url=BASE, access_token=TOKEN)
        assert me == {"user_id": "@portal-bot:matrix.mage.ru"}

    async def test_401_raises_with_errcode(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(
                401, json={"errcode": "M_UNKNOWN_TOKEN", "error": "Unrecognised access token"}
            ),
            monkeypatch,
        )
        with pytest.raises(MatrixApiError) as ei:
            await whoami(homeserver_url=BASE, access_token="bad")
        assert ei.value.status_code == 401
        assert ei.value.errcode == "M_UNKNOWN_TOKEN"

    async def test_token_whitespace_stripped_in_auth_header(self, monkeypatch):
        """Легаси-токен с хвостовым пробелом (сохранён до валидатора схемы) —
        strip в _auth_headers: h11 иначе отвергает Bearer-заголовок ещё до
        отправки («Illegal header value»)."""
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"user_id": "@b:s"})

        _make_client(handler, monkeypatch)
        me = await whoami(homeserver_url=BASE, access_token=f"{TOKEN} ")
        assert captured["auth"] == f"Bearer {TOKEN}"
        assert me == {"user_id": "@b:s"}


# ── send_message ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSendMessage:
    async def test_success_returns_event_id(self, monkeypatch):
        _make_client(lambda req: httpx.Response(200, json={"event_id": "$abc"}), monkeypatch)
        result = await send_message(
            homeserver_url=BASE,
            access_token=TOKEN,
            room_id="!room:matrix.mage.ru",
            txn_id="txn-1",
            body="hi",
        )
        assert result == {"event_id": "$abc"}

    async def test_request_shape_and_headers(self, monkeypatch):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            # url.path декодирует percent-encoding; str(url) — сохраняет.
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"event_id": "$x"})

        _make_client(handler, monkeypatch)
        await send_message(
            homeserver_url=BASE + "/",  # трейлинг-слэш нормализуется
            access_token=TOKEN,
            room_id="!room:matrix.mage.ru",
            txn_id="txn-42",
            body="plain",
            formatted_body="<b>plain</b>",
        )
        assert captured["method"] == "PUT"
        assert captured["url"].endswith(
            "/_matrix/client/v3/rooms/%21room%3Amatrix.mage.ru/send/m.room.message/txn-42"
        )
        assert captured["auth"] == f"Bearer {TOKEN}"
        assert captured["body"] == {
            "msgtype": "m.text",
            "body": "plain",
            "format": "org.matrix.custom.html",
            "formatted_body": "<b>plain</b>",
        }

    async def test_no_formatted_body_when_absent(self, monkeypatch):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"event_id": "$x"})

        _make_client(handler, monkeypatch)
        await send_message(
            homeserver_url=BASE,
            access_token=TOKEN,
            room_id="!r:s",
            txn_id="t",
            body="plain only",
        )
        assert captured["body"] == {"msgtype": "m.text", "body": "plain only"}

    async def test_429_raises_with_errcode(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(
                429, json={"errcode": "M_LIMIT_EXCEEDED", "error": "Too many requests"}
            ),
            monkeypatch,
        )
        with pytest.raises(MatrixApiError) as ei:
            await send_message(
                homeserver_url=BASE, access_token=TOKEN, room_id="!r:s", txn_id="t", body="x"
            )
        assert ei.value.status_code == 429
        assert ei.value.errcode == "M_LIMIT_EXCEEDED"

    async def test_transport_error_raises_no_status(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("read timeout")

        _make_client(handler, monkeypatch)
        with pytest.raises(MatrixApiError) as ei:
            await send_message(
                homeserver_url=BASE, access_token=TOKEN, room_id="!r:s", txn_id="t", body="x"
            )
        assert ei.value.status_code is None

    async def test_non_json_2xx_does_not_crash(self, monkeypatch):
        _make_client(lambda req: httpx.Response(200, content=b"<html>gateway</html>"), monkeypatch)
        result = await send_message(
            homeserver_url=BASE, access_token=TOKEN, room_id="!r:s", txn_id="t", body="x"
        )
        assert "_raw" in result


# ── create_dm / m.direct ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateDm:
    async def test_success_returns_room_id(self, monkeypatch):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"room_id": "!new:s"})

        _make_client(handler, monkeypatch)
        room = await create_dm(homeserver_url=BASE, access_token=TOKEN, invite_user_id="@u:s")
        assert room == "!new:s"
        assert captured["body"]["is_direct"] is True
        assert captured["body"]["invite"] == ["@u:s"]
        assert captured["body"]["preset"] == "trusted_private_chat"

    async def test_400_unknown_user(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(
                400, json={"errcode": "M_UNKNOWN", "error": "User does not exist"}
            ),
            monkeypatch,
        )
        with pytest.raises(MatrixApiError) as ei:
            await create_dm(homeserver_url=BASE, access_token=TOKEN, invite_user_id="@ghost:s")
        assert ei.value.status_code == 400

    async def test_no_room_id_in_response(self, monkeypatch):
        _make_client(lambda req: httpx.Response(200, json={}), monkeypatch)
        with pytest.raises(MatrixApiError):
            await create_dm(homeserver_url=BASE, access_token=TOKEN, invite_user_id="@u:s")


@pytest.mark.asyncio
class TestDirectRoomsAccountData:
    async def test_404_means_empty_map(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(
                404, json={"errcode": "M_NOT_FOUND", "error": "Event not found"}
            ),
            monkeypatch,
        )
        assert (
            await get_direct_rooms(homeserver_url=BASE, access_token=TOKEN, bot_user_id="@b:s")
            == {}
        )

    async def test_valid_map_parsed_garbage_filtered(self, monkeypatch):
        _make_client(
            lambda req: httpx.Response(
                200,
                json={
                    "@u:s": ["!r1:s", "!r2:s"],
                    "@bad:s": "not-a-list",
                    "123": ["!r:s"],  # не-MXID ключ (int key сериализуется в строку)
                    "@empty:s": [],
                },
            ),
            monkeypatch,
        )
        result = await get_direct_rooms(homeserver_url=BASE, access_token=TOKEN, bot_user_id="@b:s")
        assert result == {"@u:s": ["!r1:s", "!r2:s"]}

    async def test_set_direct_room_puts_full_map(self, monkeypatch):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={})

        _make_client(handler, monkeypatch)
        await set_direct_room(
            homeserver_url=BASE,
            access_token=TOKEN,
            bot_user_id="@b:s",
            direct_map={"@u:s": ["!r:s"]},
        )
        assert captured["method"] == "PUT"
        assert captured["url"].endswith("/_matrix/client/v3/user/%40b%3As/account_data/m.direct")
        assert captured["body"] == {"@u:s": ["!r:s"]}


# ── DmResolver ───────────────────────────────────────────────────────────


def _patch_transport(monkeypatch, handler) -> None:
    """Подменить singleton-клиент клиентом с данным MockTransport-handler."""
    import app.services.matrix_messenger._client as mod

    monkeypatch.setattr(
        mod, "_MATRIX_HTTP_CLIENT", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


@pytest.mark.asyncio
class TestDmResolver:
    async def test_existing_room_reused_without_create(self, monkeypatch):
        """Комната из m.direct используется как есть — createRoom не вызывается."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/createRoom"):
                # Любой вызов createRoom — ошибка теста (комната уже есть).
                return httpx.Response(500, json={"errcode": "M_UNKNOWN"})
            if request.method == "GET" and request.url.path.endswith("account_data/m.direct"):
                return httpx.Response(200, json={"@u:s": ["!existing:s"]})
            return httpx.Response(200, json={})

        _patch_transport(monkeypatch, handler)

        resolver = DmResolver(homeserver_url=BASE, access_token=TOKEN, bot_user_id="@b:s")
        assert await resolver.resolve("@u:s") == "!existing:s"

    async def test_missing_room_created_and_cached_back(self, monkeypatch):
        """Нет комнаты → createRoom + PUT m.direct; повторный resolve — из кэша."""
        calls: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, str(request.url)))
            if request.url.path.endswith("/createRoom"):
                return httpx.Response(200, json={"room_id": "!fresh:s"})
            if request.method == "PUT" and request.url.path.endswith("account_data/m.direct"):
                return httpx.Response(200, json={})
            if request.method == "GET" and request.url.path.endswith("account_data/m.direct"):
                return httpx.Response(404, json={"errcode": "M_NOT_FOUND"})
            return httpx.Response(200, json={})

        _patch_transport(monkeypatch, handler)

        resolver = DmResolver(homeserver_url=BASE, access_token=TOKEN, bot_user_id="@b:s")
        assert await resolver.resolve("@u:s") == "!fresh:s"
        # Карта записана обратно (PUT m.direct).
        assert any(m == "PUT" and u.endswith("account_data/m.direct") for m, u in calls)
        # Второй resolve того же MXID — из кэша, без новых HTTP-вызовов.
        before = len(calls)
        assert await resolver.resolve("@u:s") == "!fresh:s"
        assert len(calls) == before

    async def test_mdirect_put_failure_does_not_fail_resolve(self, monkeypatch):
        """Провал записи кэша (PUT m.direct) не фейлит резолв — отправка важнее."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/createRoom"):
                return httpx.Response(200, json={"room_id": "!fresh:s"})
            if request.method == "PUT":
                return httpx.Response(403, json={"errcode": "M_FORBIDDEN", "error": "no"})
            if request.method == "GET":
                return httpx.Response(404, json={"errcode": "M_NOT_FOUND"})
            return httpx.Response(200, json={})

        _patch_transport(monkeypatch, handler)

        resolver = DmResolver(homeserver_url=BASE, access_token=TOKEN, bot_user_id="@b:s")
        assert await resolver.resolve("@u:s") == "!fresh:s"


# ── classify_http_error ──────────────────────────────────────────────────


class TestClassifyHttpError:
    def test_5xx_is_transient(self):
        assert classify_http_error(MatrixApiError("boom", status_code=500)) == "transient"

    def test_429_is_transient(self):
        assert classify_http_error(MatrixApiError("limit", status_code=429)) == "transient"

    def test_401_is_permanent(self):
        assert classify_http_error(MatrixApiError("unauthorized", status_code=401)) == "permanent"

    def test_403_is_permanent(self):
        assert classify_http_error(MatrixApiError("forbidden", status_code=403)) == "permanent"

    def test_400_is_permanent(self):
        assert classify_http_error(MatrixApiError("bad", status_code=400)) == "permanent"

    def test_timeout_is_transient(self):
        assert classify_http_error(httpx.TimeoutException("t")) == "transient"

    def test_network_error_is_transient(self):
        assert classify_http_error(httpx.ConnectError("nope")) == "transient"

    def test_unknown_is_unknown(self):
        assert classify_http_error(RuntimeError("weird")) == "unknown"

    def test_matrix_error_without_status_is_unknown(self):
        assert classify_http_error(MatrixApiError("transport only")) == "unknown"
