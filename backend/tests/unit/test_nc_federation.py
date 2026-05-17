"""Unit-тесты для services/nc_federation.py и api/nc_federation.py.

Покрытие:
services:
- _redis_key: формат ключа
- store_initiator: генерирует токен, сохраняет в Redis с TTL
- lookup_initiator: возвращает dict, None при промахе, None при невалидном JSON
- create_temp_public_share: happy path, HTTP != 200, OCS failure, no token
- delete_temp_share: share_id=0 → no-op, 200/404 → ok, exception → silent
- request_initiator_direct_url: happy path, HTTP error, OCS error, empty url

api:
- _ocs_response: envelope shape, status field ok/failure
- federation_remote_wopi_token: token not found → OCS 404; token found → OCS 200
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_redis(get_return=None):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=get_return)
    redis.set = AsyncMock(return_value=True)
    return redis


def _make_httpx_client(status_code: int, json_body: dict, method: str = "post"):
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_body)

    client = AsyncMock()
    setattr(client, method, AsyncMock(return_value=response))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ── _redis_key ────────────────────────────────────────────────────────────────


class TestRedisKey:
    def test_prefix_and_token(self):
        from app.services.nc_federation import _REDIS_PREFIX, _redis_key

        key = _redis_key("mytoken")
        assert key == f"{_REDIS_PREFIX}mytoken"

    def test_different_tokens_produce_different_keys(self):
        from app.services.nc_federation import _redis_key

        assert _redis_key("a") != _redis_key("b")


# ── store_initiator ───────────────────────────────────────────────────────────


class TestStoreInitiator:
    async def test_returns_string_token(self):
        from app.services.nc_federation import store_initiator

        redis = _make_redis()
        token = await store_initiator(redis, user_id="u1", display_name="Alice")
        assert isinstance(token, str)
        assert len(token) > 10

    async def test_calls_redis_set_with_ttl(self):
        from app.services.nc_federation import _TOKEN_TTL_SECONDS, store_initiator

        redis = _make_redis()
        token = await store_initiator(
            redis, user_id="u1", display_name="Alice", avatar="https://av"
        )
        redis.set.assert_called_once()
        call_args = redis.set.call_args
        assert call_args[1]["ex"] == _TOKEN_TTL_SECONDS
        stored = json.loads(call_args[0][1])
        assert stored["userId"] == "u1"
        assert stored["displayName"] == "Alice"
        assert stored["avatar"] == "https://av"

    async def test_key_contains_token(self):
        from app.services.nc_federation import _REDIS_PREFIX, store_initiator

        redis = _make_redis()
        token = await store_initiator(redis, user_id="u1", display_name="Bob")
        stored_key = redis.set.call_args[0][0]
        assert stored_key == f"{_REDIS_PREFIX}{token}"

    async def test_unique_tokens_per_call(self):
        from app.services.nc_federation import store_initiator

        redis = _make_redis()
        t1 = await store_initiator(redis, user_id="u1", display_name="A")
        t2 = await store_initiator(redis, user_id="u1", display_name="A")
        assert t1 != t2


# ── lookup_initiator ──────────────────────────────────────────────────────────


class TestLookupInitiator:
    async def test_returns_dict_on_hit(self):
        from app.services.nc_federation import lookup_initiator

        payload = {"userId": "u1", "displayName": "Alice"}
        redis = _make_redis(get_return=json.dumps(payload))
        result = await lookup_initiator(redis, "tok")
        assert result == payload

    async def test_returns_none_on_miss(self):
        from app.services.nc_federation import lookup_initiator

        redis = _make_redis(get_return=None)
        assert await lookup_initiator(redis, "missing") is None

    async def test_returns_none_on_invalid_json(self):
        from app.services.nc_federation import lookup_initiator

        redis = _make_redis(get_return="not-json{{{")
        assert await lookup_initiator(redis, "bad") is None

    async def test_returns_none_on_empty_string(self):
        from app.services.nc_federation import lookup_initiator

        redis = _make_redis(get_return="")
        assert await lookup_initiator(redis, "empty") is None


# ── create_temp_public_share ──────────────────────────────────────────────────


class TestCreateTempPublicShare:
    async def test_happy_path_returns_token_and_id(self):
        from app.services.nc_federation import create_temp_public_share

        ocs_body = {
            "ocs": {
                "meta": {"statuscode": 100, "status": "ok"},
                "data": {"token": "share_abc", "id": "42"},
            }
        }
        client = _make_httpx_client(200, ocs_body, method="post")

        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            token, share_id = await create_temp_public_share(
                nc_url="https://nc.local",
                basic_auth="dXNlcjpwYXNz",
                nc_relative_path="/PortalFiles/doc.xlsx",
            )

        assert token == "share_abc"
        assert share_id == 42

    async def test_http_non_200_raises(self):
        from app.services.nc_federation import create_temp_public_share

        client = _make_httpx_client(403, {}, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="HTTP 403"):
                await create_temp_public_share(
                    nc_url="https://nc.local",
                    basic_auth="auth",
                    nc_relative_path="/f.docx",
                )

    async def test_ocs_statuscode_failure_raises(self):
        from app.services.nc_federation import create_temp_public_share

        ocs_body = {
            "ocs": {
                "meta": {"statuscode": 997, "status": "failure", "message": "Forbidden"},
                "data": {},
            }
        }
        client = _make_httpx_client(200, ocs_body, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="OCS"):
                await create_temp_public_share(
                    nc_url="https://nc.local",
                    basic_auth="auth",
                    nc_relative_path="/f.docx",
                )

    async def test_missing_token_in_response_raises(self):
        from app.services.nc_federation import create_temp_public_share

        ocs_body = {
            "ocs": {
                "meta": {"statuscode": 100, "status": "ok"},
                "data": {"token": "", "id": "1"},
            }
        }
        client = _make_httpx_client(200, ocs_body, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="no token"):
                await create_temp_public_share(
                    nc_url="https://nc.local",
                    basic_auth="auth",
                    nc_relative_path="/f.docx",
                )

    async def test_expire_date_format_is_valid_iso_date(self):
        """12.3.5 — expireDate sent to NC must be a parseable ISO date (YYYY-MM-DD)."""
        import re

        from app.services.nc_federation import create_temp_public_share

        captured_data: dict = {}

        async def _fake_post(url, *, headers, params, data):
            captured_data.update(data)
            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(
                return_value={
                    "ocs": {
                        "meta": {"statuscode": 100, "status": "ok"},
                        "data": {"token": "tok123", "id": "5"},
                    }
                }
            )
            return resp

        client = AsyncMock()
        client.post = _fake_post
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await create_temp_public_share(
                nc_url="https://nc.local",
                basic_auth="auth",
                nc_relative_path="/f.docx",
            )

        expire_date = captured_data.get("expireDate", "")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", expire_date), (
            f"expireDate must be YYYY-MM-DD, got: {expire_date!r}"
        )

    @pytest.mark.parametrize(
        "can_write,expected_permissions",
        [(True, "3"), (False, "1")],
    )
    async def test_can_write_controls_share_permissions(
        self, can_write: bool, expected_permissions: str
    ):
        """can_write=False must create a read-only share (permissions=1).

        This is the only real read-only enforcement in the Collabora flow:
        Nextcloud will set UserCanWrite=false in the WOPI session based on
        the share's permissions field, which Collabora honours server-side.
        """
        from app.services.nc_federation import create_temp_public_share

        captured_data: dict = {}

        async def _fake_post(url, *, headers, params, data):
            captured_data.update(data)
            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(
                return_value={
                    "ocs": {
                        "meta": {"statuscode": 100, "status": "ok"},
                        "data": {"token": "tok", "id": "1"},
                    }
                }
            )
            return resp

        client = AsyncMock()
        client.post = _fake_post
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await create_temp_public_share(
                nc_url="https://nc.local",
                basic_auth="auth",
                nc_relative_path="/PortalFiles/doc.xlsx",
                can_write=can_write,
            )

        assert captured_data.get("permissions") == expected_permissions

    async def test_default_can_write_is_read_plus_update(self):
        """Default (no flag) must remain backwards compatible: permissions=3."""
        from app.services.nc_federation import create_temp_public_share

        captured_data: dict = {}

        async def _fake_post(url, *, headers, params, data):
            captured_data.update(data)
            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(
                return_value={
                    "ocs": {
                        "meta": {"statuscode": 100, "status": "ok"},
                        "data": {"token": "tok", "id": "1"},
                    }
                }
            )
            return resp

        client = AsyncMock()
        client.post = _fake_post
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await create_temp_public_share(
                nc_url="https://nc.local",
                basic_auth="auth",
                nc_relative_path="/PortalFiles/doc.xlsx",
            )

        assert captured_data.get("permissions") == "3"

    async def test_token_ttl_matches_share_expiry(self):
        """12.3.5 — _TOKEN_TTL_SECONDS must cover the share expiry (hours param)."""
        from app.services.nc_federation import _TOKEN_TTL_SECONDS

        default_share_hours = 2
        assert default_share_hours * 3600 <= _TOKEN_TTL_SECONDS, (
            f"Redis TTL ({_TOKEN_TTL_SECONDS}s) must be >= share expiry "
            f"({default_share_hours * 3600}s)"
        )


# ── delete_temp_share ─────────────────────────────────────────────────────────


class TestDeleteTempShare:
    async def test_zero_share_id_is_noop(self):
        from app.services.nc_federation import delete_temp_share

        with patch("app.services.nc_federation.httpx.AsyncClient") as mock_cls:
            await delete_temp_share(nc_url="https://nc.local", basic_auth="auth", share_id=0)
            mock_cls.assert_not_called()

    async def test_200_response_no_exception(self):
        from app.services.nc_federation import delete_temp_share

        client = _make_httpx_client(200, {}, method="delete")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await delete_temp_share(nc_url="https://nc.local", basic_auth="auth", share_id=7)

    async def test_404_response_no_exception(self):
        from app.services.nc_federation import delete_temp_share

        client = _make_httpx_client(404, {}, method="delete")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await delete_temp_share(nc_url="https://nc.local", basic_auth="auth", share_id=7)

    async def test_exception_is_swallowed(self):
        from app.services.nc_federation import delete_temp_share

        client = AsyncMock()
        client.delete = AsyncMock(side_effect=ConnectionError("timeout"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            await delete_temp_share(nc_url="https://nc.local", basic_auth="auth", share_id=5)


# ── request_initiator_direct_url ──────────────────────────────────────────────


class TestRequestInitiatorDirectUrl:
    async def test_happy_path_returns_url(self):
        from app.services.nc_federation import request_initiator_direct_url

        ocs_body = {
            "ocs": {
                "meta": {"statuscode": 100},
                "data": {"url": "https://collabora.local/edit/xyz"},
            }
        }
        client = _make_httpx_client(200, ocs_body, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            url = await request_initiator_direct_url(
                nc_url="https://nc.local",
                portal_base_url="https://portal.local/",
                initiator_token="tok123",
                share_token="share456",
            )
        assert url == "https://collabora.local/edit/xyz"

    async def test_http_error_raises(self):
        from app.services.nc_federation import request_initiator_direct_url

        client = _make_httpx_client(500, {}, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                await request_initiator_direct_url(
                    nc_url="https://nc.local",
                    portal_base_url="https://portal.local",
                    initiator_token="t",
                    share_token="s",
                )

    async def test_ocs_error_raises(self):
        from app.services.nc_federation import request_initiator_direct_url

        ocs_body = {"ocs": {"meta": {"statuscode": 997}, "data": {}}}
        client = _make_httpx_client(200, ocs_body, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="OCS error"):
                await request_initiator_direct_url(
                    nc_url="https://nc.local",
                    portal_base_url="https://portal.local",
                    initiator_token="t",
                    share_token="s",
                )

    async def test_empty_url_raises(self):
        from app.services.nc_federation import request_initiator_direct_url

        ocs_body = {"ocs": {"meta": {"statuscode": 100}, "data": {"url": ""}}}
        client = _make_httpx_client(200, ocs_body, method="post")
        with patch("app.services.nc_federation.httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="empty url"):
                await request_initiator_direct_url(
                    nc_url="https://nc.local",
                    portal_base_url="https://portal.local",
                    initiator_token="t",
                    share_token="s",
                )


# ── api: _ocs_response ────────────────────────────────────────────────────────


class TestOcsResponse:
    def test_2xx_status_is_ok(self):
        from app.api.nc_federation import _ocs_response

        resp = _ocs_response(200, "OK", {"key": "val"})
        body = resp.body
        parsed = json.loads(body)
        assert parsed["ocs"]["meta"]["status"] == "ok"
        assert parsed["ocs"]["meta"]["statuscode"] == 200
        assert parsed["ocs"]["data"] == {"key": "val"}

    def test_non_2xx_status_is_failure(self):
        from app.api.nc_federation import _ocs_response

        resp = _ocs_response(404, "Not Found", [])
        parsed = json.loads(resp.body)
        assert parsed["ocs"]["meta"]["status"] == "failure"
        assert parsed["ocs"]["meta"]["statuscode"] == 404

    def test_http_status_always_200(self):
        from app.api.nc_federation import _ocs_response

        resp = _ocs_response(404, "Not Found", [])
        assert resp.status_code == 200


# ── api: federation_remote_wopi_token ─────────────────────────────────────────


class TestFederationRemoteWopiToken:
    async def test_unknown_token_returns_ocs_404(self, client):
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator", new=AsyncMock(return_value=None)
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": "unknown-token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ocs"]["meta"]["statuscode"] == 404

    async def test_known_token_returns_display_name(self, client):
        info = {"userId": "u1", "displayName": "Alice Иванова", "avatar": ""}
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator", new=AsyncMock(return_value=info)
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": "valid-token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ocs"]["meta"]["statuscode"] == 200
        data = body["ocs"]["data"]
        assert data["guestDisplayname"] == "Alice Иванова"
        assert data["editorUid"] == "u1"
        assert data["canwrite"] is True
        assert data["tokenType"] == 4

    async def test_known_token_null_userid(self, client):
        info = {"userId": None, "displayName": "Guest", "avatar": ""}
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator", new=AsyncMock(return_value=info)
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": "guest-token"},
            )
        body = resp.json()
        assert body["ocs"]["data"]["editorUid"] is None


# ── TTL-expiry contract (A4 / E18) ────────────────────────────────────────────


class TestTokenTtlExpiry:
    """Документирует поведение при истечении TTL токена и при невалидных токенах."""

    async def test_expired_token_lookup_returns_none(self):
        """Redis возвращает None (TTL истёк) → lookup_initiator возвращает None."""
        from app.services.nc_federation import lookup_initiator

        redis = _make_redis(get_return=None)
        result = await lookup_initiator(redis, "ttl-expired-token-abc123")
        assert result is None

    async def test_token_stored_with_correct_ttl(self):
        """TTL токена должен совпадать с _TOKEN_TTL_SECONDS."""
        from app.services.nc_federation import _TOKEN_TTL_SECONDS, store_initiator

        redis = _make_redis()
        await store_initiator(redis, user_id="u1", display_name="Alice")
        stored_ex = redis.set.call_args[1]["ex"]
        assert stored_ex == _TOKEN_TTL_SECONDS, (
            f"Expected TTL={_TOKEN_TTL_SECONDS}, got {stored_ex}"
        )

    async def test_api_returns_ocs_404_for_expired_token(self, client):
        """После истечения TTL (Redis miss) API возвращает OCS 404 без ошибки."""
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": "ttl-expired-token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ocs"]["meta"]["statuscode"] == 404
        assert body["ocs"]["meta"]["status"] == "failure"

    async def test_api_returns_ocs_404_for_unknown_token(self, client):
        """Неизвестный/поддельный токен → OCS 404 (защита от brute-force DoS)."""
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": "attacker-guessed-token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ocs"]["meta"]["statuscode"] == 404

    async def test_api_returns_ocs_404_for_empty_token(self, client):
        """Пустой токен → OCS 404, не 500."""
        with patch(
            "app.api.nc_federation.fed_service.lookup_initiator",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                "/ocs/v2.php/apps/richdocuments/api/v1/federation",
                data={"token": ""},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ocs"]["meta"]["statuscode"] == 404
