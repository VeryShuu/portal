"""NextcloudService — facade combining WebDAVClient + CollaboraClient.

All operations use a single 'portal-svc' account with HTTP Basic auth (App Password).
Nextcloud is used as dumb storage; ACL is enforced on the portal side.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.core.logging import get_logger

from .collabora import CollaboraClient
from .webdav import WebDAVClient

logger = get_logger(__name__)


class NextcloudService(WebDAVClient):
    """Full-featured Nextcloud service: WebDAV operations + Collabora Online.

    Inherits all WebDAV methods from WebDAVClient and delegates
    Collabora-specific methods to an internal CollaboraClient instance.
    """

    def __init__(self, nc_url: str, username: str, app_password: str, files_root: str) -> None:
        super().__init__(nc_url, username, app_password, files_root)
        self._collabora = CollaboraClient(self)

    async def get_collabora_url(self, file_nc_path: str, display_name: str) -> dict[str, Any]:
        """Legacy direct-edit flow. Prefer ``get_collabora_url_via_federation`` for new code."""
        return await self._collabora.get_collabora_url(file_nc_path, display_name)

    async def get_collabora_url_via_federation(
        self,
        *,
        file_nc_path: str,
        portal_base_url: str,
        redis: Any,
        user_id: str,
        display_name: str,
        avatar: str = "",
    ) -> dict[str, Any]:
        """Open file in Collabora via richdocuments federation initiator flow."""
        return await self._collabora.get_collabora_url_via_federation(
            file_nc_path=file_nc_path,
            portal_base_url=portal_base_url,
            redis=redis,
            user_id=user_id,
            display_name=display_name,
            avatar=avatar,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_service: NextcloudService | None = None


def get_nc_service() -> NextcloudService:
    global _service
    if _service is None:
        from app.core.system_config import load_system_settings

        sys = load_system_settings()
        _service = NextcloudService(
            nc_url=sys.nextcloud_url,
            username=sys.nc_service_username,
            app_password=sys.nc_service_app_password,
            files_root=sys.nc_files_root,
        )
    return _service


async def invalidate_nc_service() -> None:
    global _service
    if _service is not None:
        with contextlib.suppress(Exception):
            await _service.aclose()
    _service = None
