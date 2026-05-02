"""WebDAV client for Nextcloud.

Handles all file-level operations via the WebDAV protocol:
PROPFIND, MKCOL, GET, PUT, DELETE, MOVE.
"""

from __future__ import annotations

import base64
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, unquote, urlparse

import defusedxml.ElementTree as ET  # noqa: N817
import httpx

from app.core.logging import get_logger
from app.schemas.files import NCItem

logger = get_logger(__name__)

_TIMEOUT_LIST = httpx.Timeout(30.0)
_TIMEOUT_DOWNLOAD = httpx.Timeout(None)
_TIMEOUT_UPLOAD = httpx.Timeout(600.0)
_TIMEOUT_HEALTH = httpx.Timeout(3.0)

_DAV_NS = "DAV:"


class NextcloudError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class WebDAVClient:
    """Stateless WebDAV client — instantiate per-request or as singleton."""

    def __init__(self, nc_url: str, username: str, app_password: str, files_root: str) -> None:
        self._nc_url = nc_url.rstrip("/")
        self._username = username
        self._files_root = files_root
        raw = f"{username}:{app_password}".encode()
        self._basic_auth = base64.b64encode(raw).decode()
        self._client: httpx.AsyncClient | None = None

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"Authorization": f"Basic {self._basic_auth}"}
        if extra:
            h.update(extra)
        return h

    def _get_shared_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=_TIMEOUT_LIST,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _webdav_url(self, nc_path: str) -> str:
        """nc_path is relative to files_root, e.g. 'HR/Docs' or '' for root."""
        full = f"{self._files_root}/{nc_path.lstrip('/')}" if nc_path else self._files_root
        encoded = "/".join(quote(seg, safe="") for seg in full.split("/"))
        return f"{self._nc_url}/remote.php/dav/files/{self._username}/{encoded}"

    @staticmethod
    def _parse_propfind(xml_body: bytes, root_url: str) -> list[NCItem]:
        root = ET.fromstring(xml_body)
        items: list[NCItem] = []
        root_url_norm = root_url.rstrip("/")
        root_path_norm = unquote(urlparse(root_url_norm).path).rstrip("/")

        for resp in root.iter(f"{{{_DAV_NS}}}response"):
            href_el = resp.find(f"{{{_DAV_NS}}}href")
            if href_el is None or href_el.text is None:
                continue
            href = href_el.text

            prop = resp.find(f".//{{{_DAV_NS}}}prop")
            if prop is None:
                continue

            is_dir_el = prop.find(f"{{{_DAV_NS}}}resourcetype/{{{_DAV_NS}}}collection")
            is_dir = is_dir_el is not None

            size_el = prop.find(f"{{{_DAV_NS}}}getcontentlength")
            size = int(size_el.text or "0") if size_el is not None and size_el.text else 0

            mime_el = prop.find(f"{{{_DAV_NS}}}getcontenttype")
            mime = mime_el.text if mime_el is not None else None

            lm_el = prop.find(f"{{{_DAV_NS}}}getlastmodified")
            last_modified: datetime | None = None
            if lm_el is not None and lm_el.text:
                with contextlib.suppress(Exception):
                    last_modified = parsedate_to_datetime(lm_el.text)

            etag_el = prop.find(f"{{{_DAV_NS}}}getetag")
            etag = (etag_el.text or "").strip('"') if etag_el is not None else None

            href_decoded = unquote(href)
            name = href_decoded.rstrip("/").rsplit("/", 1)[-1]

            href_path_norm = unquote(urlparse(href_decoded).path).rstrip("/")
            if href_path_norm == root_path_norm:
                continue

            nc_path = href_decoded

            items.append(
                NCItem(
                    name=name,
                    nc_path=nc_path,
                    is_dir=is_dir,
                    size_bytes=size,
                    mime_type=mime,
                    last_modified=last_modified,
                    etag=etag,
                )
            )
        return items

    def _resolve_url(self, nc_path: str) -> str:
        """Resolve nc_path to a full URL.

        If nc_path is already a full DAV href (starts with /remote.php/), prepend nc_url only.
        Otherwise treat as relative path and use _webdav_url().
        """
        if nc_path.startswith("/remote.php/"):
            return f"{self._nc_url}{nc_path}"
        return self._webdav_url(nc_path)

    def _nc_relative_path(self, file_nc_path: str) -> str:
        """Extract path relative to NC username root from DAV href or relative path."""
        _dav_prefix = f"/remote.php/dav/files/{self._username}"
        if file_nc_path.startswith(_dav_prefix):
            return unquote(file_nc_path[len(_dav_prefix) :])
        if file_nc_path.startswith("/remote.php/"):
            return ""
        return f"/{file_nc_path.lstrip('/')}"

    def href_to_db_nc_path(self, href: str) -> str | None:
        """Convert decoded DAV href to DB nc_path (relative to files_root).

        Returns None if the href refers to the root folder itself.
        Input may be URL-encoded or already decoded (as returned by _parse_propfind).
        """
        decoded = unquote(href).rstrip("/")
        dav_prefix = f"/remote.php/dav/files/{self._username}/{self._files_root}"
        if not decoded.startswith(dav_prefix):
            return None
        rest = decoded[len(dav_prefix) :]
        if rest == "" or rest == "/":
            return None
        return rest.lstrip("/")

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_HEALTH) as client:
                r = await client.get(f"{self._nc_url}/status.php", headers=self._headers())
                return r.status_code == 200
        except Exception:
            return False

    async def detailed_health_check(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "configured": True,
            "server_reachable": False,
            "nc_version": None,
            "auth_ok": False,
            "webdav_ok": False,
            "details": None,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_HEALTH) as client:
                r = await client.get(f"{self._nc_url}/status.php")
                if r.status_code == 200:
                    result["server_reachable"] = True
                    try:
                        data = r.json()
                        result["nc_version"] = data.get("versionstring")
                    except Exception:
                        pass
                else:
                    result["details"] = f"Сервер вернул HTTP {r.status_code}"
                    return result
        except Exception as exc:
            result["details"] = f"Сервер недоступен: {exc}"
            return result

        dav_body = (
            b'<?xml version="1.0"?>'
            b'<D:propfind xmlns:D="DAV:"><D:prop><D:displayname/></D:prop></D:propfind>'
        )
        dav_url = f"{self._nc_url}/remote.php/dav/files/{self._username}/"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_HEALTH) as client:
                r = await client.request(
                    "PROPFIND",
                    dav_url,
                    headers={**self._headers(), "Depth": "0", "Content-Type": "application/xml"},
                    content=dav_body,
                )
                if r.status_code == 207:
                    result["auth_ok"] = True
                    result["webdav_ok"] = True
                    result["ok"] = True
                elif r.status_code == 401:
                    result["details"] = "Неверные учётные данные (401 Unauthorized)"
                elif r.status_code == 404:
                    result["auth_ok"] = True
                    result["details"] = "Пользователь или папка не найдены (404)"
                else:
                    result["details"] = f"WebDAV вернул HTTP {r.status_code}"
        except Exception as exc:
            result["details"] = f"Ошибка WebDAV: {exc}"

        return result

    async def ensure_root(self) -> None:
        """Create root PortalFiles folder in NC if it doesn't exist."""
        url = self._webdav_url("")
        client = self._get_shared_client()
        r = await client.request("MKCOL", url, headers=self._headers())
        if r.status_code not in (201, 405):
            logger.warning("nc.ensure_root_failed", status=r.status_code)

    async def list_folder(self, nc_path: str) -> list[NCItem]:
        url = self._webdav_url(nc_path)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<D:propfind xmlns:D="DAV:">'
            "<D:prop>"
            "<D:resourcetype/>"
            "<D:getcontentlength/>"
            "<D:getcontenttype/>"
            "<D:getlastmodified/>"
            "<D:getetag/>"
            "</D:prop>"
            "</D:propfind>"
        )
        headers = self._headers({"Depth": "1", "Content-Type": "application/xml"})
        client = self._get_shared_client()
        r = await client.request("PROPFIND", url, headers=headers, content=body.encode())
        if r.status_code == 404:
            raise NextcloudError(404, f"Folder not found: {nc_path}")
        if r.status_code not in (207,):
            raise NextcloudError(r.status_code, f"PROPFIND failed: {r.status_code}")
        return self._parse_propfind(r.content, url)

    async def create_folder(self, nc_path: str) -> None:
        url = self._webdav_url(nc_path)
        client = self._get_shared_client()
        r = await client.request("MKCOL", url, headers=self._headers())
        if r.status_code == 409:
            await self.ensure_root()
            r = await client.request("MKCOL", url, headers=self._headers())
        if r.status_code not in (201, 405):
            raise NextcloudError(r.status_code, f"MKCOL failed: {r.status_code}")

    async def delete(self, nc_path: str) -> None:
        url = self._resolve_url(nc_path)
        client = self._get_shared_client()
        r = await client.request("DELETE", url, headers=self._headers())
        if r.status_code not in (204, 404):
            raise NextcloudError(r.status_code, f"DELETE failed: {r.status_code}")

    async def move(self, nc_path_src: str, nc_path_dst: str) -> None:
        url_src = self._webdav_url(nc_path_src)
        url_dst = self._webdav_url(nc_path_dst)
        headers = self._headers({"Destination": url_dst, "Overwrite": "F"})
        client = self._get_shared_client()
        r = await client.request("MOVE", url_src, headers=headers)
        if r.status_code not in (201, 204):
            raise NextcloudError(r.status_code, f"MOVE failed: {r.status_code}")

    async def download_stream(self, nc_path: str) -> tuple[httpx.Response, httpx.AsyncClient]:
        """Returns (response, client). Caller must close client after consuming response.

        nc_path can be a relative path (e.g. 'PortalFiles/HR/doc.xlsx') or a full DAV href.
        """
        url = self._resolve_url(nc_path)
        client = httpx.AsyncClient(timeout=_TIMEOUT_DOWNLOAD)
        req = client.build_request("GET", url, headers=self._headers())
        r = await client.send(req, stream=True)
        if r.status_code == 404:
            await client.aclose()
            raise NextcloudError(404, f"File not found: {nc_path}")
        if r.status_code != 200:
            await client.aclose()
            raise NextcloudError(r.status_code, f"GET failed: {r.status_code}")
        return r, client

    async def upload_stream(
        self,
        nc_path: str,
        stream: AsyncIterator[bytes],
        content_type: str = "application/octet-stream",
    ) -> None:
        url = self._webdav_url(nc_path)
        headers = self._headers({"Content-Type": content_type})
        async with httpx.AsyncClient(timeout=_TIMEOUT_UPLOAD) as client:
            r = await client.put(url, headers=headers, content=stream)
        if r.status_code not in (200, 201, 204):
            raise NextcloudError(r.status_code, f"PUT failed: {r.status_code}")

    async def _get_file_nc_id(self, dav_url: str) -> str:
        """Get Nextcloud numeric file ID via PROPFIND on the DAV URL."""
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<D:propfind xmlns:D="DAV:" xmlns:oc="http://owncloud.org/ns">'
            "<D:prop><oc:fileid/></D:prop>"
            "</D:propfind>"
        )
        headers = self._headers({"Depth": "0", "Content-Type": "application/xml"})
        client = self._get_shared_client()
        r = await client.request("PROPFIND", dav_url, headers=headers, content=body.encode())
        if r.status_code not in (207,):
            raise NextcloudError(r.status_code, f"PROPFIND for fileId failed: {r.status_code}")
        root = ET.fromstring(r.content)
        fileid_el = root.find(".//{http://owncloud.org/ns}fileid")
        if fileid_el is None or not fileid_el.text:
            raise NextcloudError(500, "Could not get numeric fileId from Nextcloud")
        return fileid_el.text.strip()

    async def list_folders_recursive(self, max_depth: int = 20) -> list[str]:
        """BFS traversal of folders under files_root.

        Returns list of nc_paths (relative to files_root) in BFS order —
        parents are always listed before their children.
        """
        from collections import deque

        queue: deque[str] = deque([""])
        result: list[str] = []
        visited: set[str] = set()
        depth = 0

        while queue and depth < max_depth:
            next_level: list[str] = []
            while queue:
                current_path = queue.popleft()
                try:
                    items = await self.list_folder(current_path)
                except NextcloudError:
                    continue
                for item in items:
                    if not item.is_dir:
                        continue
                    db_path = self.href_to_db_nc_path(item.nc_path)
                    if db_path is None or db_path in visited:
                        continue
                    visited.add(db_path)
                    result.append(db_path)
                    next_level.append(db_path)
            queue = deque(next_level)
            depth += 1

        return result
