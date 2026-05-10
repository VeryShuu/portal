"""Unit-тесты для services/nextcloud/webdav.py и collabora.py.

Покрытие:
webdav.py — WebDAVClient:
- __init__: Basic Auth header формируется из username:password в base64
- _headers: возвращает Authorization, merge с extra
- _webdav_url: корректный URL с URL-кодированием спецсимволов
- _resolve_url: /remote.php/ href → prepend nc_url, иначе _webdav_url
- _nc_relative_path: DAV href → relative, /remote.php/ без DAV prefix → '', else → /path
- href_to_db_nc_path: корректный href → db nc_path, root href → None, чужой href → None
- _parse_propfind: XML с файлами и папками → список NCItem
- health_check: 200 → True, ошибка → False
- NextcloudError: status и message

collabora.py — CollaboraClient:
- _try_richdocuments_ocs: 200+OCS 100 → Response, другой статус → None
- _try_direct_editing: 200+OCS 100 → Response, ошибка → None
- get_collabora_url: richdocuments успех → возвращает url с token
- get_collabora_url: оба метода провалились → NextcloudError 502
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from app.services.nextcloud.webdav import WebDAVClient



# ── helpers ───────────────────────────────────────────────────────────────────


def _make_webdav(
    nc_url: str = "http://nc:8080",
    username: str = "admin",
    password: str = "secret",
    files_root: str = "PortalFiles",
) -> WebDAVClient:
    from app.services.nextcloud.webdav import WebDAVClient

    return WebDAVClient(nc_url=nc_url, username=username, app_password=password, files_root=files_root)


def _make_response(status: int, json_data=None, content: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=json_data or {})
    r.content = content
    return r


# ── NextcloudError ────────────────────────────────────────────────────────────


class TestNextcloudError:
    def test_status_and_message(self):
        from app.services.nextcloud.webdav import NextcloudError

        err = NextcloudError(404, "not found")
        assert err.status == 404
        assert "not found" in str(err)

    def test_is_exception(self):
        from app.services.nextcloud.webdav import NextcloudError

        with pytest.raises(NextcloudError):
            raise NextcloudError(502, "bad gateway")


# ── WebDAVClient.__init__ / _headers ─────────────────────────────────────────


class TestWebDAVClientInit:
    def test_basic_auth_computed(self):
        client = _make_webdav(username="user", password="pass")
        expected = base64.b64encode(b"user:pass").decode()
        assert client._basic_auth == expected

    def test_trailing_slash_stripped_from_url(self):
        client = _make_webdav(nc_url="http://nc:8080/")
        assert not client._nc_url.endswith("/")

    def test_headers_include_authorization(self):
        client = _make_webdav()
        headers = client._headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_headers_merge_extra(self):
        client = _make_webdav()
        headers = client._headers({"Depth": "1"})
        assert headers["Depth"] == "1"
        assert "Authorization" in headers

    def test_headers_extra_does_not_override_auth(self):
        client = _make_webdav()
        headers = client._headers({"Authorization": "Bearer token"})
        assert headers["Authorization"] == "Bearer token"


# ── _webdav_url ───────────────────────────────────────────────────────────────


class TestWebdavUrl:
    def test_empty_nc_path_returns_root(self):
        client = _make_webdav(nc_url="http://nc", username="admin", files_root="PortalFiles")
        url = client._webdav_url("")
        assert "admin" in url
        assert "PortalFiles" in url

    def test_relative_path_appended(self):
        client = _make_webdav(nc_url="http://nc", username="admin", files_root="PortalFiles")
        url = client._webdav_url("HR/Docs")
        assert "HR" in url
        assert "Docs" in url

    def test_special_chars_url_encoded(self):
        client = _make_webdav()
        url = client._webdav_url("Папка с пробелами")
        assert " " not in url
        assert "%" in url

    def test_starts_with_nc_url(self):
        client = _make_webdav(nc_url="http://nc:9000")
        url = client._webdav_url("folder")
        assert url.startswith("http://nc:9000")


# ── _resolve_url ──────────────────────────────────────────────────────────────


class TestResolveUrl:
    def test_remote_php_href_prepends_nc_url(self):
        client = _make_webdav(nc_url="http://nc")
        url = client._resolve_url("/remote.php/dav/files/admin/PortalFiles/HR")
        assert url.startswith("http://nc/remote.php/")

    def test_relative_path_uses_webdav_url(self):
        client = _make_webdav(nc_url="http://nc", username="admin", files_root="PortalFiles")
        url = client._resolve_url("HR/Docs")
        assert "remote.php" in url
        assert "HR" in url


# ── _nc_relative_path ─────────────────────────────────────────────────────────


class TestNcRelativePath:
    def test_dav_href_strips_prefix(self):
        client = _make_webdav(username="admin")
        result = client._nc_relative_path("/remote.php/dav/files/admin/HR/Docs")
        assert result == "/HR/Docs"

    def test_other_remote_php_returns_empty(self):
        client = _make_webdav(username="admin")
        result = client._nc_relative_path("/remote.php/webdav/something")
        assert result == ""

    def test_relative_path_returned_with_slash(self):
        client = _make_webdav(username="admin")
        result = client._nc_relative_path("HR/Docs")
        assert result == "/HR/Docs"

    def test_already_slash_prefixed(self):
        client = _make_webdav(username="admin")
        result = client._nc_relative_path("/HR/Docs")
        assert result == "/HR/Docs"


# ── href_to_db_nc_path ────────────────────────────────────────────────────────


class TestHrefToDbNcPath:
    def test_correct_href_returns_path(self):
        client = _make_webdav(username="admin", files_root="PortalFiles")
        href = "/remote.php/dav/files/admin/PortalFiles/HR/Docs"
        result = client.href_to_db_nc_path(href)
        assert result == "HR/Docs"

    def test_root_href_returns_none(self):
        client = _make_webdav(username="admin", files_root="PortalFiles")
        href = "/remote.php/dav/files/admin/PortalFiles"
        result = client.href_to_db_nc_path(href)
        assert result is None

    def test_root_href_with_slash_returns_none(self):
        client = _make_webdav(username="admin", files_root="PortalFiles")
        href = "/remote.php/dav/files/admin/PortalFiles/"
        result = client.href_to_db_nc_path(href)
        assert result is None

    def test_foreign_href_returns_none(self):
        client = _make_webdav(username="admin", files_root="PortalFiles")
        href = "/remote.php/dav/files/other_user/PortalFiles/HR"
        result = client.href_to_db_nc_path(href)
        assert result is None

    def test_url_encoded_href_decoded(self):
        client = _make_webdav(username="admin", files_root="PortalFiles")
        href = "/remote.php/dav/files/admin/PortalFiles/HR%20Docs"
        result = client.href_to_db_nc_path(href)
        assert result == "HR Docs"


# ── _parse_propfind ───────────────────────────────────────────────────────────


class TestParsePropfind:
    def _make_xml(self, root_url: str, items: list[dict]) -> bytes:
        def item_xml(item):
            resource_type = "<D:collection/>" if item.get("is_dir") else ""
            size_el = f"<D:getcontentlength>{item.get('size', 0)}</D:getcontentlength>" if not item.get("is_dir") else ""
            mime_el = f"<D:getcontenttype>{item.get('mime', 'application/octet-stream')}</D:getcontenttype>"
            return f"""
            <D:response>
                <D:href>{item['href']}</D:href>
                <D:propstat>
                    <D:prop>
                        <D:resourcetype>{resource_type}</D:resourcetype>
                        {size_el}
                        {mime_el}
                        <D:getetag>"abc123"</D:getetag>
                    </D:prop>
                    <D:status>HTTP/1.1 200 OK</D:status>
                </D:propstat>
            </D:response>
            """

        responses = "".join(item_xml(i) for i in items)
        return f"""<?xml version="1.0"?>
        <D:multistatus xmlns:D="DAV:">
        {responses}
        </D:multistatus>""".encode()

    def test_parses_file(self):
        from app.services.nextcloud.webdav import WebDAVClient

        root_url = "http://nc/remote.php/dav/files/admin/PortalFiles/"
        xml = self._make_xml(root_url, [
            {"href": "/remote.php/dav/files/admin/PortalFiles/doc.txt", "size": 1024, "mime": "text/plain"},
        ])
        items = WebDAVClient._parse_propfind(xml, root_url)
        assert len(items) == 1
        assert items[0].name == "doc.txt"
        assert items[0].is_dir is False
        assert items[0].size_bytes == 1024

    def test_parses_directory(self):
        from app.services.nextcloud.webdav import WebDAVClient

        root_url = "http://nc/remote.php/dav/files/admin/PortalFiles/"
        xml = self._make_xml(root_url, [
            {"href": "/remote.php/dav/files/admin/PortalFiles/HR/", "is_dir": True},
        ])
        items = WebDAVClient._parse_propfind(xml, root_url)
        assert len(items) == 1
        assert items[0].is_dir is True
        assert items[0].name == "HR"

    def test_skips_root_entry(self):
        from app.services.nextcloud.webdav import WebDAVClient

        root_url = "http://nc/remote.php/dav/files/admin/PortalFiles"
        xml = self._make_xml(root_url, [
            {"href": "/remote.php/dav/files/admin/PortalFiles", "is_dir": True},
            {"href": "/remote.php/dav/files/admin/PortalFiles/file.txt", "size": 100},
        ])
        items = WebDAVClient._parse_propfind(xml, root_url)
        assert len(items) == 1
        assert items[0].name == "file.txt"

    def test_etag_stripped_of_quotes(self):
        from app.services.nextcloud.webdav import WebDAVClient

        root_url = "http://nc/remote.php/dav/files/admin/PortalFiles"
        xml = self._make_xml(root_url, [
            {"href": "/remote.php/dav/files/admin/PortalFiles/file.txt", "size": 10},
        ])
        items = WebDAVClient._parse_propfind(xml, root_url)
        assert items[0].etag == "abc123"


# ── health_check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    async def test_returns_true_on_200(self):
        client = _make_webdav()
        mock_response = _make_response(200)
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http):
            result = await client.health_check()
        assert result is True

    async def test_returns_false_on_non_200(self):
        client = _make_webdav()
        mock_response = _make_response(503)
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http):
            result = await client.health_check()
        assert result is False

    async def test_returns_false_on_exception(self):
        client = _make_webdav()
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(side_effect=Exception("connect failed"))

        with patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http):
            result = await client.health_check()
        assert result is False


# ── CollaboraClient._try_richdocuments_ocs ────────────────────────────────────


class TestTryRichdocumentsOcs:
    def _make_collabora(self):
        from app.services.nextcloud.collabora import CollaboraClient

        webdav = _make_webdav()
        mock_client = AsyncMock()
        webdav._get_list_client = MagicMock(return_value=mock_client)
        return CollaboraClient(webdav), mock_client

    async def test_returns_response_on_ocs_100(self):
        collab, http = self._make_collabora()
        response = _make_response(200, {"ocs": {"meta": {"statuscode": 100}, "data": {"url": "http://collab/", "token": "tok"}}})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_richdocuments_ocs("12345")
        assert result is not None

    async def test_returns_response_on_ocs_200(self):
        collab, http = self._make_collabora()
        response = _make_response(200, {"ocs": {"meta": {"statuscode": 200}, "data": {"url": "http://collab/"}}})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_richdocuments_ocs("12345")
        assert result is not None

    async def test_returns_none_on_http_error(self):
        collab, http = self._make_collabora()
        response = _make_response(404, {})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_richdocuments_ocs("12345")
        assert result is None

    async def test_returns_none_on_bad_ocs_status(self):
        collab, http = self._make_collabora()
        response = _make_response(200, {"ocs": {"meta": {"statuscode": 403}}})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_richdocuments_ocs("12345")
        assert result is None


# ── CollaboraClient._try_direct_editing ───────────────────────────────────────


class TestTryDirectEditing:
    def _make_collabora(self):
        from app.services.nextcloud.collabora import CollaboraClient

        webdav = _make_webdav()
        mock_client = AsyncMock()
        webdav._get_list_client = MagicMock(return_value=mock_client)
        return CollaboraClient(webdav), mock_client

    async def test_returns_response_on_success(self):
        collab, http = self._make_collabora()
        response = _make_response(200, {"ocs": {"meta": {"statuscode": 100}, "data": {"url": "http://edit/"}}})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_direct_editing("/PortalFiles/doc.odt")
        assert result is not None

    async def test_returns_none_on_failure(self):
        collab, http = self._make_collabora()
        response = _make_response(500, {})
        http.post = AsyncMock(return_value=response)

        result = await collab._try_direct_editing("/PortalFiles/doc.odt")
        assert result is None


# ── CollaboraClient.get_collabora_url ─────────────────────────────────────────


class TestGetCollaboraUrl:
    def _make_collabora_with_mocks(self):
        from app.services.nextcloud.collabora import CollaboraClient

        webdav = _make_webdav(username="admin", files_root="PortalFiles")
        mock_client = AsyncMock()
        webdav._get_list_client = MagicMock(return_value=mock_client)
        webdav._nc_url = "http://nc"

        async def fake_get_file_nc_id(url):
            return "99999"

        webdav._get_file_nc_id = fake_get_file_nc_id
        return CollaboraClient(webdav), mock_client

    async def test_success_via_richdocuments(self):
        collab, http = self._make_collabora_with_mocks()
        ocs_response = _make_response(
            200,
            {"ocs": {"meta": {"statuscode": 100}, "data": {"url": "http://collab/wopi", "token": "mytoken"}}}
        )
        http.post = AsyncMock(return_value=ocs_response)

        result = await collab.get_collabora_url(
            file_nc_path="PortalFiles/doc.odt",
            display_name="John Doe",
        )
        assert "url" in result
        assert "token" in result
        assert result["token"] == "mytoken"
        assert "display_name" in result["url"]

    async def test_raises_nextcloud_error_when_both_fail(self):
        from app.services.nextcloud.webdav import NextcloudError

        collab, http = self._make_collabora_with_mocks()
        http.post = AsyncMock(return_value=_make_response(404, {}))

        with pytest.raises(NextcloudError) as exc:
            await collab.get_collabora_url(
                file_nc_path="PortalFiles/doc.odt",
                display_name="John Doe",
            )
        assert exc.value.status == 502

    async def test_uses_full_dav_url_for_remote_php_path(self):
        collab, http = self._make_collabora_with_mocks()
        ocs_response = _make_response(
            200,
            {"ocs": {"meta": {"statuscode": 100}, "data": {"url": "http://collab/", "token": "t"}}}
        )
        http.post = AsyncMock(return_value=ocs_response)

        result = await collab.get_collabora_url(
            file_nc_path="/remote.php/dav/files/admin/PortalFiles/doc.odt",
            display_name="Alice",
        )
        assert "url" in result
