"""Unit-тесты services/nextcloud/webdav.py (Фаза 3.5).

Покрытие:
- WebDAVClient._webdav_url: пустой путь / путь с частями
- WebDAVClient._resolve_url: начинается с /remote.php/ / относительный путь
- WebDAVClient._nc_relative_path: dav prefix / /remote.php/ / relative
- WebDAVClient.href_to_db_nc_path: корневая папка → None / файл → rel path / чужой href → None
- WebDAVClient._parse_propfind: пустой XML (только root) / файл / папка / без href
- WebDAVClient.health_check: 200 → True / exception → False
- WebDAVClient.list_folder: 207 успех / 404 → NextcloudError / другой статус → NextcloudError
- WebDAVClient.create_folder: 201 успех / 409 → ensure_root + retry / error → NextcloudError
- WebDAVClient.delete: 204 / 404 (silent) / error → NextcloudError
- WebDAVClient.move: 201 / 204 / error → NextcloudError
- WebDAVClient._headers: basic auth / extra headers
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_client(
    nc_url: str = "https://nc.example.com",
    username: str = "portal",
    password: str = "secret",
    files_root: str = "PortalFiles",
):
    from app.services.nextcloud.webdav import WebDAVClient

    return WebDAVClient(nc_url, username, password, files_root)


def _mock_response(status: int, content: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = content
    return r


# ── _webdav_url ───────────────────────────────────────────────────────────────


def test_webdav_url_empty_path():
    client = _make_client()
    url = client._webdav_url("")
    assert "nc.example.com" in url
    assert "portal" in url
    assert "PortalFiles" in url


def test_webdav_url_with_path():
    client = _make_client()
    url = client._webdav_url("HR/Docs")
    assert "HR" in url
    assert "Docs" in url


def test_webdav_url_encodes_special_chars():
    client = _make_client()
    url = client._webdav_url("my folder/file name.txt")
    assert " " not in url


def test_webdav_url_leading_slash_stripped():
    client = _make_client()
    url1 = client._webdav_url("HR/Docs")
    url2 = client._webdav_url("/HR/Docs")
    assert url1 == url2


# ── _resolve_url ──────────────────────────────────────────────────────────────


def test_resolve_url_dav_href():
    client = _make_client()
    href = "/remote.php/dav/files/portal/PortalFiles/HR/doc.xlsx"
    url = client._resolve_url(href)
    assert url.startswith("https://nc.example.com")
    assert "/remote.php/" in url


def test_resolve_url_relative():
    client = _make_client()
    url = client._resolve_url("HR/Docs")
    assert "nc.example.com" in url
    assert "PortalFiles" in url


# ── _nc_relative_path ─────────────────────────────────────────────────────────


def test_nc_relative_path_from_dav_prefix():
    client = _make_client()
    href = "/remote.php/dav/files/portal/PortalFiles/HR/doc.xlsx"
    result = client._nc_relative_path(href)
    assert result == "/PortalFiles/HR/doc.xlsx"


def test_nc_relative_path_from_remote_php():
    client = _make_client()
    href = "/remote.php/webdav/something"
    result = client._nc_relative_path(href)
    assert result == ""


def test_nc_relative_path_from_relative():
    client = _make_client()
    result = client._nc_relative_path("HR/Docs")
    assert result == "/HR/Docs"


# ── href_to_db_nc_path ────────────────────────────────────────────────────────


def test_href_to_db_nc_path_root_returns_none():
    client = _make_client()
    href = "/remote.php/dav/files/portal/PortalFiles"
    result = client.href_to_db_nc_path(href)
    assert result is None


def test_href_to_db_nc_path_file():
    client = _make_client()
    href = "/remote.php/dav/files/portal/PortalFiles/HR/doc.xlsx"
    result = client.href_to_db_nc_path(href)
    assert result == "HR/doc.xlsx"


def test_href_to_db_nc_path_foreign_href():
    client = _make_client()
    result = client.href_to_db_nc_path("/remote.php/dav/files/other/SomePath/file.txt")
    assert result is None


def test_href_to_db_nc_path_nested():
    client = _make_client()
    href = "/remote.php/dav/files/portal/PortalFiles/A/B/C/file.doc"
    result = client.href_to_db_nc_path(href)
    assert result == "A/B/C/file.doc"


# ── _headers ─────────────────────────────────────────────────────────────────


def test_headers_contains_basic_auth():
    client = _make_client(username="portal", password="secret")
    headers = client._headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")

    decoded = base64.b64decode(headers["Authorization"][6:]).decode()
    assert decoded == "portal:secret"


def test_headers_with_extra():
    client = _make_client()
    headers = client._headers({"Depth": "1", "Content-Type": "application/xml"})
    assert headers["Depth"] == "1"
    assert headers["Content-Type"] == "application/xml"
    assert "Authorization" in headers


# ── _parse_propfind ───────────────────────────────────────────────────────────


def test_parse_propfind_empty_multistatus():
    from app.services.nextcloud.webdav import WebDAVClient

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    root_url = "https://nc.example.com/remote.php/dav/files/portal/PortalFiles/"
    items = WebDAVClient._parse_propfind(xml, root_url)
    assert items == []


def test_parse_propfind_file_item():
    from app.services.nextcloud.webdav import WebDAVClient

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/doc.xlsx</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype/>
        <D:getcontentlength>1234</D:getcontentlength>
        <D:getcontenttype>application/vnd.openxmlformats-officedocument.spreadsheetml.sheet</D:getcontenttype>
        <D:getetag>"abc123"</D:getetag>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    root_url = "https://nc.example.com/remote.php/dav/files/portal/PortalFiles/"
    items = WebDAVClient._parse_propfind(xml, root_url)
    assert len(items) == 1
    assert items[0].name == "doc.xlsx"
    assert items[0].is_dir is False
    assert items[0].size_bytes == 1234


def test_parse_propfind_directory_item():
    from app.services.nextcloud.webdav import WebDAVClient

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/HR/</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/></D:resourcetype>
        <D:getcontentlength>0</D:getcontentlength>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    root_url = "https://nc.example.com/remote.php/dav/files/portal/PortalFiles/"
    items = WebDAVClient._parse_propfind(xml, root_url)
    assert len(items) == 1
    assert items[0].name == "HR"
    assert items[0].is_dir is True


def test_parse_propfind_no_href_element():
    from app.services.nextcloud.webdav import WebDAVClient

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
  </D:response>
</D:multistatus>"""

    root_url = "https://nc.example.com/remote.php/dav/files/portal/PortalFiles/"
    items = WebDAVClient._parse_propfind(xml, root_url)
    assert items == []


# ── health_check ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check_success():
    client = _make_client()

    mock_response = _mock_response(200)
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_client_instance
    ):
        result = await client.health_check()

    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure_non_200():
    client = _make_client()

    mock_response = _mock_response(503)
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_client_instance
    ):
        result = await client.health_check()

    assert result is False


@pytest.mark.asyncio
async def test_health_check_exception_returns_false():
    client = _make_client()

    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(side_effect=Exception("Connection error"))
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_client_instance
    ):
        result = await client.health_check()

    assert result is False


# ── list_folder ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folder_success():

    client = _make_client()

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/</D:href>
    <D:propstat>
      <D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    mock_response = _mock_response(207, xml)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_list_client", return_value=mock_http_client):
        items = await client.list_folder("")

    assert items == []


@pytest.mark.asyncio
async def test_list_folder_not_found():
    from app.services.nextcloud.webdav import NextcloudError

    client = _make_client()
    mock_response = _mock_response(404)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with (
        patch.object(client, "_get_list_client", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc,
    ):
        await client.list_folder("HR/Missing")

    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_list_folder_server_error():
    from app.services.nextcloud.webdav import NextcloudError

    client = _make_client()
    mock_response = _mock_response(500)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with (
        patch.object(client, "_get_list_client", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc,
    ):
        await client.list_folder("HR")

    assert exc.value.status == 500


# ── create_folder ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_folder_success_201():
    client = _make_client()
    mock_response = _mock_response(201)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.create_folder("HR/NewFolder")


@pytest.mark.asyncio
async def test_create_folder_already_exists_405():
    client = _make_client()
    mock_response = _mock_response(405)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.create_folder("HR/Existing")


@pytest.mark.asyncio
async def test_create_folder_409_retries_after_ensure_root():

    client = _make_client()
    responses = [_mock_response(409), _mock_response(201)]
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(side_effect=responses)

    mock_ensure_root = AsyncMock()
    with (
        patch.object(client, "_get_mutation_client", return_value=mock_http_client),
        patch.object(client, "ensure_root", mock_ensure_root),
    ):
        await client.create_folder("HR/New")

    mock_ensure_root.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_folder_error():
    from app.services.nextcloud.webdav import NextcloudError

    client = _make_client()
    mock_response = _mock_response(500)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with (
        patch.object(client, "_get_mutation_client", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc,
    ):
        await client.create_folder("HR/Bad")

    assert exc.value.status == 500


# ── delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_success_204():
    client = _make_client()
    mock_response = _mock_response(204)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.delete("HR/file.xlsx")


@pytest.mark.asyncio
async def test_delete_not_found_404_silent():
    client = _make_client()
    mock_response = _mock_response(404)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.delete("HR/already_deleted.xlsx")


@pytest.mark.asyncio
async def test_delete_server_error():
    from app.services.nextcloud.webdav import NextcloudError

    client = _make_client()
    mock_response = _mock_response(500)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with (
        patch.object(client, "_get_mutation_client", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc,
    ):
        await client.delete("HR/file.xlsx")

    assert exc.value.status == 500


# ── move ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_move_success_201():
    client = _make_client()
    mock_response = _mock_response(201)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.move("HR/old.xlsx", "HR/new.xlsx")


@pytest.mark.asyncio
async def test_move_success_204():
    client = _make_client()
    mock_response = _mock_response(204)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.move("HR/old.xlsx", "HR/new.xlsx")


@pytest.mark.asyncio
async def test_move_conflict():
    from app.services.nextcloud.webdav import NextcloudError

    client = _make_client()
    mock_response = _mock_response(412)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_response)

    with (
        patch.object(client, "_get_mutation_client", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc,
    ):
        await client.move("HR/file.xlsx", "HR/exists.xlsx")

    assert exc.value.status == 412


# ── aclose ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aclose_closes_clients():
    import httpx

    client = _make_client()
    mock_list = AsyncMock(spec=httpx.AsyncClient)
    mock_list.is_closed = False
    mock_mutation = AsyncMock(spec=httpx.AsyncClient)
    mock_mutation.is_closed = False

    client._list_client = mock_list
    client._mutation_client = mock_mutation

    await client.aclose()

    mock_list.aclose.assert_awaited_once()
    mock_mutation.aclose.assert_awaited_once()
    assert client._list_client is None
    assert client._mutation_client is None


@pytest.mark.asyncio
async def test_aclose_noop_when_no_clients():
    client = _make_client()
    client._list_client = None
    client._mutation_client = None

    await client.aclose()


# ── detailed_health_check ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detailed_health_check_all_ok():
    client = _make_client()

    status_resp = MagicMock()
    status_resp.status_code = 200
    status_resp.json.return_value = {"versionstring": "28.0.1"}

    dav_resp = MagicMock()
    dav_resp.status_code = 207

    def _make_client_instance(*args, **kwargs):
        mock = AsyncMock()

        async def _get(url, **kw):
            return status_resp

        async def _request(method, url, **kw):
            return dav_resp

        mock.get = _get
        mock.request = _request
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)
        return mock

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", side_effect=_make_client_instance
    ):
        result = await client.detailed_health_check()

    assert result["ok"] is True
    assert result["server_reachable"] is True
    assert result["auth_ok"] is True
    assert result["nc_version"] == "28.0.1"


@pytest.mark.asyncio
async def test_detailed_health_check_server_non_200():
    client = _make_client()

    status_resp = MagicMock()
    status_resp.status_code = 503

    def _make_client_instance(*args, **kwargs):
        mock = AsyncMock()

        async def _get(url, **kw):
            return status_resp

        mock.get = _get
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)
        return mock

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", side_effect=_make_client_instance
    ):
        result = await client.detailed_health_check()

    assert result["ok"] is False
    assert result["server_reachable"] is False


@pytest.mark.asyncio
async def test_detailed_health_check_server_unreachable():
    client = _make_client()

    def _make_client_instance(*args, **kwargs):
        mock = AsyncMock()

        async def _get(url, **kw):
            raise Exception("connection refused")

        mock.get = _get
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)
        return mock

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", side_effect=_make_client_instance
    ):
        result = await client.detailed_health_check()

    assert result["ok"] is False
    assert "Сервер недоступен" in result["details"]


@pytest.mark.asyncio
async def test_detailed_health_check_webdav_401():
    client = _make_client()

    status_resp = MagicMock()
    status_resp.status_code = 200
    status_resp.json.return_value = {"versionstring": "28.0.0"}

    dav_resp = MagicMock()
    dav_resp.status_code = 401

    def _make_client_instance(*args, **kwargs):
        mock = AsyncMock()

        async def _get(url, **kw):
            return status_resp

        async def _request(method, url, **kw):
            return dav_resp

        mock.get = _get
        mock.request = _request
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=False)
        return mock

    with patch(
        "app.services.nextcloud.webdav.httpx.AsyncClient", side_effect=_make_client_instance
    ):
        result = await client.detailed_health_check()

    assert result["ok"] is False
    assert result["server_reachable"] is True
    assert result["auth_ok"] is False


# ── ensure_root ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_root_success_201():
    client = _make_client()
    mock_resp = _mock_response(201)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.ensure_root()

    mock_http_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_root_unexpected_status_logs():
    client = _make_client()
    mock_resp = _mock_response(500)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_mutation_client", return_value=mock_http_client):
        await client.ensure_root()


# ── download_stream ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_stream_success():
    import httpx

    client = _make_client()

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200

    mock_http_client = MagicMock(spec=httpx.AsyncClient)
    mock_http_client.build_request = MagicMock(return_value=MagicMock())
    mock_http_client.send = AsyncMock(return_value=mock_resp)

    with patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http_client):
        r, _c = await client.download_stream("PortalFiles/doc.pdf")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_download_stream_404_raises():
    import httpx

    from app.services.nextcloud import NextcloudError

    client = _make_client()

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404

    mock_http_client = MagicMock(spec=httpx.AsyncClient)
    mock_http_client.build_request = MagicMock(return_value=MagicMock())
    mock_http_client.send = AsyncMock(return_value=mock_resp)
    mock_http_client.aclose = AsyncMock()

    with (
        patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http_client),
        pytest.raises(NextcloudError) as exc_info,
    ):
        await client.download_stream("PortalFiles/missing.pdf")

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_download_stream_500_raises():
    import httpx

    from app.services.nextcloud import NextcloudError

    client = _make_client()

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500

    mock_http_client = MagicMock(spec=httpx.AsyncClient)
    mock_http_client.build_request = MagicMock(return_value=MagicMock())
    mock_http_client.send = AsyncMock(return_value=mock_resp)
    mock_http_client.aclose = AsyncMock()

    with (
        patch("app.services.nextcloud.webdav.httpx.AsyncClient", return_value=mock_http_client),
        pytest.raises(NextcloudError),
    ):
        await client.download_stream("PortalFiles/doc.pdf")


# ── _get_file_nc_id ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_file_nc_id_success():
    client = _make_client()

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:oc="http://owncloud.org/ns">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/doc.pdf</D:href>
    <D:propstat>
      <D:prop><oc:fileid>12345</oc:fileid></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    mock_resp = _mock_response(207, xml)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_resp)

    with patch.object(client, "_get_list_client", return_value=mock_http_client):
        nc_id = await client._get_file_nc_id(
            "https://nc.example.com/remote.php/dav/files/portal/PortalFiles/doc.pdf"
        )

    assert nc_id == "12345"


@pytest.mark.asyncio
async def test_get_file_nc_id_non_207_raises():
    from app.services.nextcloud import NextcloudError

    client = _make_client()
    mock_resp = _mock_response(404)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_resp)

    with (
        patch.object(client, "_get_list_client", return_value=mock_http_client),
        pytest.raises(NextcloudError),
    ):
        await client._get_file_nc_id("https://nc.example.com/dav/doc.pdf")


@pytest.mark.asyncio
async def test_get_file_nc_id_missing_fileid_raises():
    from app.services.nextcloud import NextcloudError

    client = _make_client()

    xml = b"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/remote.php/dav/files/portal/PortalFiles/doc.pdf</D:href>
    <D:propstat>
      <D:prop></D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    mock_resp = _mock_response(207, xml)
    mock_http_client = AsyncMock()
    mock_http_client.request = AsyncMock(return_value=mock_resp)

    with (
        patch.object(client, "_get_list_client", return_value=mock_http_client),
        pytest.raises(NextcloudError),
    ):
        await client._get_file_nc_id("https://nc.example.com/dav/doc.pdf")


# ── list_folders_recursive ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folders_recursive_empty():
    client = _make_client()

    with patch.object(client, "list_folder", return_value=[]):
        result = await client.list_folders_recursive()

    assert result == []


@pytest.mark.asyncio
async def test_list_folders_recursive_one_level():
    from app.services.nextcloud.webdav import NCItem

    client = _make_client()

    sub1 = NCItem(
        nc_path="/remote.php/dav/files/portal/PortalFiles/HR",
        name="HR",
        is_dir=True,
        size=None,
        content_type=None,
        last_modified=None,
        etag=None,
    )
    sub2 = NCItem(
        nc_path="/remote.php/dav/files/portal/PortalFiles/Finance",
        name="Finance",
        is_dir=True,
        size=None,
        content_type=None,
        last_modified=None,
        etag=None,
    )
    file1 = NCItem(
        nc_path="/remote.php/dav/files/portal/PortalFiles/doc.pdf",
        name="doc.pdf",
        is_dir=False,
        size=1024,
        content_type="application/pdf",
        last_modified=None,
        etag=None,
    )

    async def _mock_list_folder(path):
        if path == "":
            return [sub1, sub2, file1]
        return []

    with patch.object(client, "list_folder", side_effect=_mock_list_folder):
        result = await client.list_folders_recursive()

    assert "HR" in result
    assert "Finance" in result
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_folders_recursive_error_continues():
    from app.services.nextcloud import NextcloudError

    client = _make_client()

    async def _mock_list_folder(path):
        raise NextcloudError(404, "not found")

    with patch.object(client, "list_folder", side_effect=_mock_list_folder):
        result = await client.list_folders_recursive()

    assert result == []
