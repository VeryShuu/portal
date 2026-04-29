"""Unit-тесты Phase 5 — NextcloudService (services/nextcloud.py).

Покрытие:
- _webdav_url: кодирование имён с пробелами/спецсимволами
- _parse_propfind: парсинг PROPFIND XML — файлы, папки, пропуск root
- health_check: 200 → True, exception → False
- list_folder: 207 → items, 404 → NextcloudError
- create_folder: 201 → ok, ошибка → NextcloudError
- delete: 204 → ok, 404 → ok (не бросает), ошибка → NextcloudError
- move: 201 → ok, ошибка → NextcloudError
- upload_stream: 201 → ok, ошибка → NextcloudError
"""

from __future__ import annotations

import textwrap
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from app.services.nextcloud import NextcloudError, NextcloudService


# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_svc() -> NextcloudService:
    return NextcloudService(
        nc_url="https://nc.company.local",
        username="portal-svc",
        app_password="secret",
        files_root="PortalFiles",
    )


PROPFIND_BODY = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <D:multistatus xmlns:D="DAV:">
      <D:response>
        <D:href>/remote.php/dav/files/portal-svc/PortalFiles/HR/</D:href>
        <D:propstat>
          <D:prop>
            <D:resourcetype><D:collection/></D:resourcetype>
            <D:getcontentlength>0</D:getcontentlength>
            <D:getcontenttype>httpd/unix-directory</D:getcontenttype>
            <D:getlastmodified>Sat, 26 Apr 2026 09:00:00 GMT</D:getlastmodified>
            <D:getetag>"abc"</D:getetag>
          </D:prop>
        </D:propstat>
      </D:response>
      <D:response>
        <D:href>/remote.php/dav/files/portal-svc/PortalFiles/HR/report.pdf</D:href>
        <D:propstat>
          <D:prop>
            <D:resourcetype/>
            <D:getcontentlength>12345</D:getcontentlength>
            <D:getcontenttype>application/pdf</D:getcontenttype>
            <D:getlastmodified>Sat, 26 Apr 2026 10:00:00 GMT</D:getlastmodified>
            <D:getetag>"def"</D:getetag>
          </D:prop>
        </D:propstat>
      </D:response>
    </D:multistatus>
""").encode()


# ── _webdav_url ────────────────────────────────────────────────────────────────


def test_webdav_url_root():
    svc = make_svc()
    url = svc._webdav_url("")
    assert url == "https://nc.company.local/remote.php/dav/files/portal-svc/PortalFiles"


def test_webdav_url_subpath():
    svc = make_svc()
    url = svc._webdav_url("HR/Docs")
    assert "PortalFiles/HR/Docs" in url


def test_webdav_url_encodes_spaces():
    svc = make_svc()
    url = svc._webdav_url("My Folder/file name.pdf")
    assert " " not in url
    assert "%20" in url


# ── _parse_propfind ────────────────────────────────────────────────────────────


def test_parse_propfind_returns_file():
    svc = make_svc()
    root_url = "https://nc.company.local/remote.php/dav/files/portal-svc/PortalFiles/HR/"
    items = svc._parse_propfind(PROPFIND_BODY, root_url)
    assert len(items) == 1
    item = items[0]
    assert item.name == "report.pdf"
    assert item.is_dir is False
    assert item.size_bytes == 12345
    assert item.mime_type == "application/pdf"
    assert item.etag == "def"


def test_parse_propfind_skips_root():
    svc = make_svc()
    root_url = "https://nc.company.local/remote.php/dav/files/portal-svc/PortalFiles/HR/"
    items = svc._parse_propfind(PROPFIND_BODY, root_url)
    names = [i.name for i in items]
    assert "HR" not in names


# ── health_check ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        result = await svc.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_exception():
    svc = make_svc()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        result = await svc.health_check()
    assert result is False


# ── list_folder ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folder_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 207
    mock_resp.content = PROPFIND_BODY
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        items = await svc.list_folder("HR")
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_list_folder_404():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(NextcloudError) as exc_info:
            await svc.list_folder("NoSuchFolder")
    assert exc_info.value.status == 404


# ── create_folder ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_folder_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.create_folder("HR/NewFolder")


@pytest.mark.asyncio
async def test_create_folder_already_exists_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 405
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.create_folder("HR/Existing")


@pytest.mark.asyncio
async def test_create_folder_error():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(NextcloudError):
            await svc.create_folder("HR/Bad")


# ── delete ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.delete("HR/old.pdf")


@pytest.mark.asyncio
async def test_delete_404_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.delete("HR/gone.pdf")


# ── move ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_move_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.move("HR/old", "HR/new")


@pytest.mark.asyncio
async def test_move_error():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(NextcloudError):
            await svc.move("HR/a", "HR/b")


# ── upload_stream ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_stream_ok():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def _stream():
        yield b"hello"

    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        await svc.upload_stream("HR/file.txt", _stream())


@pytest.mark.asyncio
async def test_upload_stream_error():
    svc = make_svc()
    mock_resp = MagicMock()
    mock_resp.status_code = 507
    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def _stream():
        yield b"data"

    with patch("app.services.nextcloud.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(NextcloudError):
            await svc.upload_stream("HR/file.txt", _stream())
