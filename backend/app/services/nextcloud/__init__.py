"""Nextcloud integration package.

Public API (re-exported for backward compatibility):
  - NextcloudService  — facade: WebDAV + Collabora operations
  - WebDAVClient      — raw WebDAV operations only
  - CollaboraClient   — Collabora Online operations (takes WebDAVClient)
  - NextcloudError    — exception raised on NC errors
  - get_nc_service()  — sync accessor (auto-rebuilds on settings change)
  - get_nextcloud_service() — async FastAPI ``Depends`` factory
  - invalidate_nc_service() — invalidate cached instance (call after settings change)
"""

import httpx  # noqa: F401  # re-exported so patch("app.services.nextcloud.httpx") still works

from .collabora import CollaboraClient
from .service import (
    NextcloudService,
    get_nc_service,
    get_nextcloud_service,
    invalidate_nc_service,
)
from .webdav import NextcloudError, WebDAVClient

__all__ = [
    "CollaboraClient",
    "NextcloudError",
    "NextcloudService",
    "WebDAVClient",
    "get_nc_service",
    "get_nextcloud_service",
    "invalidate_nc_service",
]
