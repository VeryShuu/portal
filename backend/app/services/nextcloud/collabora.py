"""Collabora Online client for Nextcloud.

Handles richdocuments OCS, Direct Editing API, and federation initiator flow.
Requires a WebDAVClient instance for shared connection and auth helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from app.core.logging import get_logger

if TYPE_CHECKING:
    from .webdav import WebDAVClient

logger = get_logger(__name__)

_OCS_BASE = "/ocs/v2.php/apps/richdocuments/api/v1/document"
_DISPLAY_NAME_MAX_LEN = 200


class CollaboraClient:
    """Collabora Online integration — wraps a WebDAVClient for auth and connection."""

    def __init__(self, webdav: WebDAVClient) -> None:
        self._webdav = webdav

    async def _try_richdocuments_ocs(self, file_id: str) -> httpx.Response | None:
        """Try richdocuments OCS open endpoint with fileId query param.

        Note: this endpoint does not honour any read-only flag — write enforcement
        for legacy callers is the responsibility of ``get_collabora_url``.
        """
        nc_url = self._webdav._nc_url
        headers = self._webdav._headers({"OCS-APIRequest": "true", "Accept": "application/json"})
        client = self._webdav._get_list_client()
        for base in [f"{nc_url}{_OCS_BASE}", f"{nc_url}/index.php{_OCS_BASE}"]:
            r = await client.post(
                base,
                headers=headers,
                params={"format": "json", "fileId": file_id},
            )
            logger.info("nc.collabora_richdoc_attempt", url=base, status=r.status_code)
            if r.status_code == 200:
                ocs_status = r.json().get("ocs", {}).get("meta", {}).get("statuscode", 0)
                if ocs_status in (100, 200):
                    return r
        return None

    async def _try_direct_editing(self, nc_path: str) -> httpx.Response | None:
        """Try NC core Direct Editing API (files app, works without richdocuments OCS).

        Note: this endpoint does not honour any read-only flag — write enforcement
        for legacy callers is the responsibility of ``get_collabora_url``.
        """
        nc_url = self._webdav._nc_url
        url = f"{nc_url}/ocs/v2.php/apps/files/api/v1/directEditing/open"
        headers = self._webdav._headers({"OCS-APIRequest": "true", "Accept": "application/json"})
        client = self._webdav._get_list_client()
        r = await client.post(
            url,
            headers=headers,
            params={"format": "json", "path": nc_path, "editorId": "richdocuments"},
        )
        logger.info("nc.collabora_directedit_attempt", status=r.status_code)
        if r.status_code == 200:
            ocs_status = r.json().get("ocs", {}).get("meta", {}).get("statuscode", 0)
            if ocs_status in (100, 200):
                return r
        return None

    async def get_collabora_url(
        self, file_nc_path: str, display_name: str, *, can_write: bool = True
    ) -> dict[str, Any]:
        """Legacy direct-edit flow (no real user name in Collabora).

        Kept as a fallback. Prefer ``get_collabora_url_via_federation`` for new code.

        ``can_write=False`` is NOT enforceable through richdocuments OCS / directEditing
        (neither endpoint honours a read-only flag). To avoid silently granting write
        access to a viewer, we refuse to open the document in this mode.
        """
        from .webdav import NextcloudError

        if not can_write:
            raise NextcloudError(
                502,
                "Read-only Collabora is not supported in legacy fallback flow; "
                "configure portal_base_url to enable federation flow.",
            )

        display_name = display_name[:_DISPLAY_NAME_MAX_LEN]
        webdav = self._webdav

        if file_nc_path.startswith("/remote.php/"):
            dav_url = f"{webdav._nc_url}{file_nc_path}"
        else:
            dav_url = webdav._webdav_url(file_nc_path)

        nc_path = webdav._nc_relative_path(file_nc_path)
        file_id = await webdav._get_file_nc_id(dav_url)
        logger.info("nc.collabora_open", file_id=file_id, nc_path=nc_path)

        r = await self._try_richdocuments_ocs(file_id)
        if r is not None:
            ocs_data = r.json().get("ocs", {}).get("data", {})
            wopi_url = ocs_data.get("url", "")
            token = ocs_data.get("token", "")
            sep = "&" if "?" in wopi_url else "?"
            return {"url": f"{wopi_url}{sep}display_name={quote(display_name)}", "token": token}

        if nc_path:
            r = await self._try_direct_editing(nc_path)
            if r is not None:
                editor_url = r.json().get("ocs", {}).get("data", {}).get("url", "")
                if editor_url:
                    return {"url": editor_url, "token": ""}

        raise NextcloudError(
            502,
            "Cannot open file in Collabora: richdocuments OCS and directEditing both failed "
            f"for path={nc_path!r}, fileId={file_id!r}",
        )

    async def get_collabora_url_via_federation(
        self,
        *,
        file_nc_path: str,
        portal_base_url: str,
        redis: Any,
        user_id: str,
        display_name: str,
        avatar: str = "",
        can_write: bool = True,
    ) -> dict[str, Any]:
        """Open file in Collabora via richdocuments federation initiator flow.

        Returns ``{"url": <direct-edit URL>}``. Nextcloud will call back to
        ``portal_base_url`` to fetch the display name when Collabora opens
        the document, so the real user name appears in collaborative cursors.
        """
        display_name = display_name[:_DISPLAY_NAME_MAX_LEN]
        from app.services import nc_federation as fed

        from .webdav import NextcloudError

        webdav = self._webdav
        if file_nc_path.startswith(f"/remote.php/dav/files/{webdav._username}"):
            from urllib.parse import unquote as _unquote

            nc_relative = _unquote(file_nc_path[len(f"/remote.php/dav/files/{webdav._username}") :])
        elif file_nc_path.startswith("/remote.php/"):
            nc_relative = ""
        else:
            nc_relative = f"/{webdav._files_root.strip('/')}/{file_nc_path.lstrip('/')}"
        if not nc_relative:
            raise NextcloudError(400, f"Cannot derive NC-relative path from {file_nc_path!r}")

        try:
            share_token, share_id = await fed.create_temp_public_share(
                nc_url=webdav._nc_url,
                basic_auth=webdav._basic_auth,
                nc_relative_path=nc_relative,
                can_write=can_write,
            )
        except Exception as exc:
            logger.warning(
                "nc.fed_share_create_failed_fallback",
                error=str(exc),
                nc_path=nc_relative,
            )
            return await self.get_collabora_url(file_nc_path, display_name, can_write=can_write)

        initiator_token = await fed.store_initiator(
            redis,
            user_id=user_id,
            display_name=display_name,
            avatar=avatar,
        )
        try:
            direct_url = await fed.request_initiator_direct_url(
                nc_url=webdav._nc_url,
                portal_base_url=portal_base_url,
                initiator_token=initiator_token,
                share_token=share_token,
            )
        except Exception as exc:
            logger.warning("nc.fed_initiator_call_failed", error=str(exc))
            await redis.delete(f"rd:fed_initiator:{initiator_token}")
            await fed.delete_temp_share(
                nc_url=webdav._nc_url,
                basic_auth=webdav._basic_auth,
                share_id=share_id,
            )
            raise NextcloudError(502, f"Federation handshake failed: {exc}") from exc

        logger.info(
            "nc.collabora_federation_opened",
            user_id=user_id,
            nc_path=nc_relative,
            initiator_token_prefix=initiator_token[:8],
        )
        return {"url": direct_url, "token": ""}
