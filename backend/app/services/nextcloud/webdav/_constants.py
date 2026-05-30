from __future__ import annotations

import httpx

_TIMEOUT_LIST = httpx.Timeout(15.0)
_TIMEOUT_MUTATION = httpx.Timeout(60.0)
_TIMEOUT_DOWNLOAD = httpx.Timeout(None)
_TIMEOUT_UPLOAD = httpx.Timeout(600.0)
_TIMEOUT_HEALTH = httpx.Timeout(3.0)

_DAV_NS = "DAV:"
