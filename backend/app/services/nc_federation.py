"""Federation initiator flow for opening Nextcloud files in Collabora
with the real portal user's display name (ADR-032 compliant).

High-level flow (per richdocuments OCSController/FederationController):

1. Portal generates a random initiator token and stores
   ``{userId, displayName, avatar}`` in Redis under that token.
2. Portal creates a short-lived public share for the file in Nextcloud
   (via OCS files_sharing API, expireDate ≈ 2h).
3. Portal POSTs to Nextcloud
   ``/ocs/v2.php/apps/richdocuments/api/v1/direct/share/initiator``
   (anonymous request) with ``initiatorServer = portal_base_url``,
   ``initiatorToken = our token`` and ``shareToken = NC share token``.
4. Nextcloud creates a direct-edit entry. When the user opens it,
   ``directView.show`` invokes ``upgradeFromDirectInitiator`` which sets
   ``wopi.remoteServer = portal_base_url`` and
   ``wopi.remoteServerToken = our initiator token``.
5. Collabora asks NC for ``CheckFileInfo``;
   ``WopiController::setFederationFileInfo`` calls
   ``FederationService::getRemoteFileDetails`` which POSTs to
   ``{portal}/ocs/v2.php/apps/richdocuments/api/v1/federation`` with form
   ``token = our initiator token``. Portal returns a Wopi-shaped payload
   whose ``guestDisplayname`` becomes the Collabora ``UserFriendlyName``.

References (nextcloud/richdocuments):
``lib/Controller/OCSController.php::createPublicFromInitiator``,
``lib/Service/FederationService.php::getRemoteFileDetails``,
``lib/Controller/WopiController.php::setFederationFileInfo``.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_TTL_SECONDS = 2 * 60 * 60  # 2 hours — must match share expireDate
_REDIS_PREFIX = "rd:fed_initiator:"


def _redis_key(token: str) -> str:
    return f"{_REDIS_PREFIX}{token}"


async def store_initiator(
    redis: Redis,
    *,
    user_id: str,
    display_name: str,
    avatar: str = "",
) -> str:
    """Generate a fresh initiator token, store user info in Redis, return token."""
    token = secrets.token_urlsafe(32)
    payload = {
        "userId": user_id,
        "displayName": display_name,
        "avatar": avatar,
    }
    await redis.set(_redis_key(token), json.dumps(payload), ex=_TOKEN_TTL_SECONDS)
    return token


async def lookup_initiator(redis: Redis, token: str) -> dict[str, Any] | None:
    """Fetch initiator info by token (used by /federation/user callback)."""
    raw = await redis.get(_redis_key(token))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


async def create_temp_public_share(
    *,
    nc_url: str,
    basic_auth: str,
    nc_relative_path: str,
    hours: int = 2,
) -> tuple[str, int]:
    """Create a public link share with an expireDate; returns (NC share token, share id).

    nc_relative_path is the path relative to portal-svc files root,
    e.g. ``/PortalFiles/HR/doc.xlsx``.
    """
    expire_at = (datetime.now(UTC) + timedelta(hours=hours, days=1)).strftime("%Y-%m-%d")
    url = f"{nc_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "OCS-APIRequest": "true",
        "Accept": "application/json",
    }
    data = {
        "path": nc_relative_path,
        "shareType": "3",  # public link
        "permissions": "3",  # read + update (so user can save edits)
        "expireDate": expire_at,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.post(url, headers=headers, params={"format": "json"}, data=data)

    if r.status_code != 200:
        logger.warning(
            "nc.fed_share_create_failed",
            status=r.status_code,
        )
        raise RuntimeError(f"Cannot create temp share: HTTP {r.status_code}")

    body = r.json().get("ocs", {})
    meta = body.get("meta", {})
    if meta.get("statuscode") not in (100, 200):
        logger.warning(
            "nc.fed_share_ocs_failure",
            ocs_statuscode=meta.get("statuscode"),
            ocs_message=meta.get("message", "")[:100],
        )
        raise RuntimeError(f"Cannot create temp share: OCS {meta}")

    share_data = body.get("data", {})
    share_token = share_data.get("token", "")
    share_id = int(share_data.get("id", 0))
    if not share_token:
        raise RuntimeError("Share created but no token returned")
    return share_token, share_id


async def delete_temp_share(
    *,
    nc_url: str,
    basic_auth: str,
    share_id: int,
) -> None:
    """Delete a public share by its NC numeric id (best-effort)."""
    if not share_id:
        return
    url = f"{nc_url}/ocs/v2.php/apps/files_sharing/api/v1/shares/{share_id}"
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "OCS-APIRequest": "true",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            r = await client.delete(url, headers=headers, params={"format": "json"})
        if r.status_code not in (200, 404):
            logger.warning("nc.fed_share_delete_failed", status=r.status_code, share_id=share_id)
    except Exception as exc:
        logger.warning("nc.fed_share_delete_error", share_id=share_id, error=str(exc))


async def request_initiator_direct_url(
    *,
    nc_url: str,
    portal_base_url: str,
    initiator_token: str,
    share_token: str,
) -> str:
    """Call NC OCS createPublicFromInitiator (anonymous). Returns direct-edit URL."""
    url = f"{nc_url}/ocs/v2.php/apps/richdocuments/api/v1/direct/share/initiator"
    headers = {
        "OCS-APIRequest": "true",
        "Accept": "application/json",
    }
    data = {
        "initiatorServer": portal_base_url.rstrip("/"),
        "initiatorToken": initiator_token,
        "shareToken": share_token,
    }
    # NB: no Authorization header — endpoint is @PublicPage and creates a
    # guest direct entry, which is exactly what we want.
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.post(url, headers=headers, params={"format": "json"}, data=data)

    if r.status_code != 200:
        logger.warning(
            "nc.fed_initiator_failed",
            status=r.status_code,
        )
        raise RuntimeError(f"createPublicFromInitiator failed: HTTP {r.status_code}")

    body = r.json().get("ocs", {})
    meta = body.get("meta", {})
    if meta.get("statuscode") not in (100, 200):
        raise RuntimeError(f"createPublicFromInitiator OCS error: {meta}")

    direct_url = body.get("data", {}).get("url", "")
    if not direct_url:
        raise RuntimeError("createPublicFromInitiator returned empty url")
    return direct_url
