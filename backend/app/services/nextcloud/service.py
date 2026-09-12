"""NextcloudService — facade combining WebDAVClient + CollaboraClient.

All operations use a single 'portal-svc' account with HTTP Basic auth (App Password).
Nextcloud is used as dumb storage; ACL is enforced on the portal side.
"""

from __future__ import annotations

import asyncio
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

    async def get_collabora_url(
        self, file_nc_path: str, display_name: str, *, can_write: bool = True
    ) -> dict[str, Any]:
        """Legacy direct-edit flow. Prefer ``get_collabora_url_via_federation`` for new code."""
        return await self._collabora.get_collabora_url(
            file_nc_path, display_name, can_write=can_write
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
        """Open file in Collabora via richdocuments federation initiator flow."""
        return await self._collabora.get_collabora_url_via_federation(
            file_nc_path=file_nc_path,
            portal_base_url=portal_base_url,
            redis=redis,
            user_id=user_id,
            display_name=display_name,
            avatar=avatar,
            can_write=can_write,
        )


# ── Module-level service factory ──────────────────────────────────────────────
#
# The factory keeps a cached `NextcloudService` instance and rebuilds it
# automatically when the relevant slice of `SystemSettings` changes
# (`nextcloud_url`, `nc_service_username`, `nc_service_app_password`,
# `nc_files_root`). `invalidate_nc_service()` is still exposed for callers that
# need explicit teardown (settings save handlers, lifespan shutdown).

_service: NextcloudService | None = None
_service_fingerprint: tuple[str, str, str, str] | None = None
_service_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _service_lock
    if _service_lock is None:
        _service_lock = asyncio.Lock()
    return _service_lock


def _current_fingerprint() -> tuple[str, str, str, str]:
    from app.core.system_config import load_system_settings

    sys = load_system_settings()
    return (
        sys.nextcloud_url,
        sys.nc_service_username,
        sys.nc_service_app_password,
        sys.nc_files_root,
    )


def _build_service(fp: tuple[str, str, str, str]) -> NextcloudService:
    nc_url, username, app_password, files_root = fp
    return NextcloudService(
        nc_url=nc_url,
        username=username,
        app_password=app_password,
        files_root=files_root,
    )


def get_nc_service() -> NextcloudService:
    """Return the cached :class:`NextcloudService`, rebuilding it when settings change.

    Synchronous accessor preserved for backward compatibility with workers,
    lifespan hooks and other non-request contexts.
    """
    global _service, _service_fingerprint
    fp = _current_fingerprint()
    if _service is None or _service_fingerprint != fp:
        # Stale service (if any) is discarded; its async httpx client will be
        # released by GC. For deterministic cleanup, prefer
        # ``invalidate_nc_service()`` from an async context.
        _service = _build_service(fp)
        _service_fingerprint = fp
    return _service


async def get_nextcloud_service() -> NextcloudService:
    """FastAPI dependency form of :func:`get_nc_service`.

    Suitable for use as ``Depends(get_nextcloud_service)`` in route signatures —
    enables per-test overrides via ``app.dependency_overrides``.
    """
    global _service, _service_fingerprint
    fp = _current_fingerprint()
    async with _get_lock():
        if _service is None or _service_fingerprint != fp:
            if _service is not None:
                with contextlib.suppress(Exception):
                    await _service.aclose()
            _service = _build_service(fp)
            _service_fingerprint = fp
        return _service


async def invalidate_nc_service() -> None:
    global _service, _service_fingerprint
    async with _get_lock():
        if _service is not None:
            with contextlib.suppress(Exception):
                await _service.aclose()
        _service = None
        _service_fingerprint = None
