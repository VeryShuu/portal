"""Unit-тесты для CollaboraClient (services/nextcloud/collabora.py).

Покрытие:
- _try_richdocuments_ocs: оба base URL / non-200 / ocs status != 100/200
- _try_direct_editing: 200+ocs ok / non-200 / ocs status error
- get_collabora_url: can_write=False → NextcloudError / richdocuments ok / direct editing fallback / both fail
- get_collabora_url_via_federation: share create fails → fallback / initiator_direct_url fails / success
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_webdav(nc_url="https://nc.example.com", username="admin", files_root="files"):
    wdav = MagicMock()
    wdav._nc_url = nc_url
    wdav._username = username
    wdav._files_root = files_root
    wdav._headers = MagicMock(return_value={"Authorization": "Basic xxx"})
    wdav._webdav_url = MagicMock(
        return_value=f"{nc_url}/remote.php/dav/files/{username}/myfile.docx"
    )
    wdav._nc_relative_path = MagicMock(return_value="/myfile.docx")
    wdav._get_file_nc_id = AsyncMock(return_value="12345")
    wdav._basic_auth = ("admin", "secret")
    client_mock = AsyncMock()
    wdav._get_list_client = MagicMock(return_value=client_mock)
    return wdav


def _make_collabora(nc_url="https://nc.example.com"):
    from app.services.nextcloud.collabora import CollaboraClient

    wdav = _make_webdav(nc_url)
    return CollaboraClient(wdav), wdav


# ── _try_richdocuments_ocs ────────────────────────────────────────────────────


class TestTryRichdocumentsOcs:
    @pytest.mark.asyncio
    async def test_returns_response_on_200_ocs_ok(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "wopi://...", "token": "tok"}}
        }
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_richdocuments_ocs("12345")
        assert result is resp

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {}
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_richdocuments_ocs("12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_ocs_status_not_ok(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ocs": {"meta": {"statuscode": 404}}}
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_richdocuments_ocs("12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_second_base_url_tried(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp_fail = MagicMock()
        resp_fail.status_code = 404
        resp_fail.json.return_value = {}
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "ocs": {"meta": {"statuscode": 200}, "data": {"url": "wopi://ok", "token": "t"}}
        }
        http_client.post = AsyncMock(side_effect=[resp_fail, resp_ok])

        result = await client._try_richdocuments_ocs("12345")
        assert result is resp_ok


# ── _try_direct_editing ───────────────────────────────────────────────────────


class TestTryDirectEditing:
    @pytest.mark.asyncio
    async def test_returns_response_on_success(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "editor://..."}}
        }
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_direct_editing("/myfile.docx")
        assert result is resp

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 500
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_direct_editing("/myfile.docx")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_ocs_status_error(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"ocs": {"meta": {"statuscode": 403}}}
        http_client.post = AsyncMock(return_value=resp)

        result = await client._try_direct_editing("/myfile.docx")
        assert result is None


# ── get_collabora_url ─────────────────────────────────────────────────────────


class TestGetCollaboraUrl:
    @pytest.mark.asyncio
    async def test_can_write_false_raises_nextcloud_error(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        with pytest.raises(NextcloudError) as exc_info:
            await client.get_collabora_url("/myfile.docx", "Alice", can_write=False)
        assert exc_info.value.status == 502

    @pytest.mark.asyncio
    async def test_richdocuments_ocs_success(self):
        client, wdav = _make_collabora()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "wopi://ok?a=1", "token": "tok"}}
        }
        wdav._get_list_client().post = AsyncMock(return_value=resp)

        result = await client.get_collabora_url("/myfile.docx", "Alice")
        assert "wopi://ok" in result["url"]
        assert result["token"] == "tok"

    @pytest.mark.asyncio
    async def test_direct_editing_fallback(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()

        fail_resp = MagicMock()
        fail_resp.status_code = 404
        fail_resp.json.return_value = {}
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "editor://me"}}
        }

        http_client.post = AsyncMock(side_effect=[fail_resp, fail_resp, ok_resp])

        result = await client.get_collabora_url("/myfile.docx", "Alice")
        assert result["url"] == "editor://me"
        assert result["token"] == ""

    @pytest.mark.asyncio
    async def test_both_fail_raises_nextcloud_error(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        fail_resp = MagicMock()
        fail_resp.status_code = 404
        fail_resp.json.return_value = {}
        http_client.post = AsyncMock(return_value=fail_resp)

        with pytest.raises(NextcloudError) as exc_info:
            await client.get_collabora_url("/myfile.docx", "Alice")
        assert exc_info.value.status == 502

    @pytest.mark.asyncio
    async def test_remote_php_path_uses_full_url(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "wopi://path", "token": "t"}}
        }
        http_client.post = AsyncMock(return_value=resp)

        result = await client.get_collabora_url("/remote.php/dav/files/admin/myfile.docx", "Bob")
        assert "wopi://path" in result["url"]

    @pytest.mark.asyncio
    async def test_display_name_truncated(self):
        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "wopi://x", "token": "t"}}
        }
        http_client.post = AsyncMock(return_value=resp)

        long_name = "A" * 300
        result = await client.get_collabora_url("/myfile.docx", long_name)
        assert "url" in result


# ── get_collabora_url_via_federation ──────────────────────────────────────────


class TestGetCollaboraUrlViaFederation:
    @pytest.mark.asyncio
    async def test_invalid_nc_path_raises(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        wdav._username = "admin"
        redis = AsyncMock()

        with pytest.raises(NextcloudError) as exc_info:
            await client.get_collabora_url_via_federation(
                file_nc_path="/remote.php/webdav/something",
                portal_base_url="https://portal.example.com",
                redis=redis,
                user_id="u1",
                display_name="Alice",
            )
        assert exc_info.value.status == 400

    @pytest.mark.asyncio
    async def test_share_create_failure_falls_back_to_legacy(self):
        client, wdav = _make_collabora()
        wdav._username = "admin"
        redis = AsyncMock()

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "ocs": {"meta": {"statuscode": 100}, "data": {"url": "wopi://fallback", "token": "t"}}
        }
        wdav._get_list_client().post = AsyncMock(return_value=resp)

        with patch(
            "app.services.nc_federation.create_temp_public_share",
            AsyncMock(side_effect=Exception("share error")),
        ):
            result = await client.get_collabora_url_via_federation(
                file_nc_path="/remote.php/dav/files/admin/doc.docx",
                portal_base_url="https://portal.example.com",
                redis=redis,
                user_id="u1",
                display_name="Alice",
            )
        assert "wopi://fallback" in result["url"]

    @pytest.mark.asyncio
    async def test_initiator_direct_url_failure_raises(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        wdav._username = "admin"
        redis = AsyncMock()
        redis.delete = AsyncMock()

        with patch(
            "app.services.nc_federation.create_temp_public_share",
            AsyncMock(return_value=("share_tok", "share_id_1")),
        ):
            with patch(
                "app.services.nc_federation.store_initiator", AsyncMock(return_value="init_tok_abc")
            ):
                with patch(
                    "app.services.nc_federation.request_initiator_direct_url",
                    AsyncMock(side_effect=Exception("timeout")),
                ):
                    with patch("app.services.nc_federation.delete_temp_share", AsyncMock()):
                        with pytest.raises(NextcloudError) as exc_info:
                            await client.get_collabora_url_via_federation(
                                file_nc_path="/remote.php/dav/files/admin/doc.docx",
                                portal_base_url="https://portal.example.com",
                                redis=redis,
                                user_id="u1",
                                display_name="Alice",
                            )
        assert exc_info.value.status == 502

    @pytest.mark.asyncio
    async def test_success_returns_direct_url(self):
        client, wdav = _make_collabora()
        wdav._username = "admin"
        redis = AsyncMock()

        with patch(
            "app.services.nc_federation.create_temp_public_share",
            AsyncMock(return_value=("share_tok", "sid")),
        ):
            with patch(
                "app.services.nc_federation.store_initiator", AsyncMock(return_value="init_abc")
            ):
                with patch(
                    "app.services.nc_federation.request_initiator_direct_url",
                    AsyncMock(return_value="https://collabora.example.com/edit/abc"),
                ):
                    result = await client.get_collabora_url_via_federation(
                        file_nc_path="/remote.php/dav/files/admin/doc.docx",
                        portal_base_url="https://portal.example.com",
                        redis=redis,
                        user_id="u1",
                        display_name="Alice",
                        avatar="https://avatar.url",
                        can_write=False,
                    )
        assert result["url"] == "https://collabora.example.com/edit/abc"
        assert result["token"] == ""

    @pytest.mark.asyncio
    async def test_nc_relative_path_from_simple_path(self):
        client, wdav = _make_collabora()
        wdav._username = "admin"
        wdav._files_root = "files"
        redis = AsyncMock()

        with patch(
            "app.services.nc_federation.create_temp_public_share",
            AsyncMock(return_value=("st", "si")),
        ):
            with patch("app.services.nc_federation.store_initiator", AsyncMock(return_value="it")):
                with patch(
                    "app.services.nc_federation.request_initiator_direct_url",
                    AsyncMock(return_value="https://collab/x"),
                ):
                    result = await client.get_collabora_url_via_federation(
                        file_nc_path="myfile.docx",
                        portal_base_url="https://portal.example.com",
                        redis=redis,
                        user_id="u1",
                        display_name="Alice",
                    )
        assert result["url"] == "https://collab/x"


# ── get_collabora_url extra branch coverage ────────────────────────────────────


class TestGetCollaboraUrlExtraBranches:
    @pytest.mark.asyncio
    async def test_empty_nc_path_skips_direct_editing(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        wdav._nc_relative_path = MagicMock(return_value="")
        http_client = wdav._get_list_client()

        fail_resp = MagicMock()
        fail_resp.status_code = 404
        fail_resp.json.return_value = {}
        http_client.post = AsyncMock(return_value=fail_resp)

        with pytest.raises(NextcloudError) as exc_info:
            await client.get_collabora_url("/remote.php/dav/files/admin/myfile.docx", "Alice")
        assert exc_info.value.status == 502

    @pytest.mark.asyncio
    async def test_direct_editing_empty_url_falls_to_error(self):
        from app.services.nextcloud.webdav import NextcloudError

        client, wdav = _make_collabora()
        http_client = wdav._get_list_client()

        fail_resp = MagicMock()
        fail_resp.status_code = 404
        fail_resp.json.return_value = {}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"ocs": {"meta": {"statuscode": 100}, "data": {"url": ""}}}

        http_client.post = AsyncMock(side_effect=[fail_resp, fail_resp, ok_resp])

        with pytest.raises(NextcloudError) as exc_info:
            await client.get_collabora_url("/myfile.docx", "Alice")
        assert exc_info.value.status == 502
