"""WebDAV client for Nextcloud.

Handles all file-level operations via the WebDAV protocol:
PROPFIND, MKCOL, GET, PUT, DELETE, MOVE.
"""

from __future__ import annotations

import defusedxml.ElementTree as ET  # noqa: N817
import httpx

from app.core.logging import get_logger
from app.schemas.files import NCItem

from ._client import WebDAVClient
from ._constants import (
    _DAV_NS,
    _TIMEOUT_DOWNLOAD,
    _TIMEOUT_HEALTH,
    _TIMEOUT_LIST,
    _TIMEOUT_MUTATION,
    _TIMEOUT_UPLOAD,
)
from ._errors import NextcloudError
from ._xml import parse_propfind

logger = get_logger(__name__)

__all__ = [
    "ET",
    "_DAV_NS",
    "_TIMEOUT_DOWNLOAD",
    "_TIMEOUT_HEALTH",
    "_TIMEOUT_LIST",
    "_TIMEOUT_MUTATION",
    "_TIMEOUT_UPLOAD",
    "NCItem",
    "NextcloudError",
    "WebDAVClient",
    "httpx",
    "logger",
    "parse_propfind",
]
