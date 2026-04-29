"""Public OCS-compatible endpoint for Nextcloud richdocuments federation callback.

When the portal opens a file in Collabora via the federation initiator flow,
it stores the initiator's user info in Redis under a random token and passes
that token to Nextcloud as ``initiatorToken``. When Collabora later opens
the document, the file-host Nextcloud calls
``FederationService::getRemoteFileDetails`` which POSTs to
``{portal}/ocs/v2.php/apps/richdocuments/api/v1/federation`` with form-encoded
``token=...`` to fetch the initiator's display name (used as the
``UserFriendlyName`` in WOPI ``CheckFileInfo``).

The expected response is a Wopi-entity-shaped JSON object that
``OCA\\Richdocuments\\Db\\Wopi::fromParams`` can hydrate; the only field that
``setFederationFileInfo`` actually reads is ``guestDisplayname``.

The endpoint is public (no auth, no CSRF) — protection comes from the
unguessable token. Tokens have a short TTL.
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from app.api.deps import RedisDep
from app.core.logging import get_logger
from app.services import nc_federation as fed_service

logger = get_logger(__name__)

router = APIRouter(tags=["nc-federation"])

# Wopi::TOKEN_TYPE_INITIATOR in richdocuments (lib/Db/Wopi.php).
_TOKEN_TYPE_INITIATOR = 4


def _ocs_response(status_code: int, message: str, data: dict | list) -> JSONResponse:
    """Wrap response in Nextcloud OCS envelope."""
    body = {
        "ocs": {
            "meta": {
                "status": "ok" if 200 <= status_code < 300 else "failure",
                "statuscode": status_code,
                "message": message,
            },
            "data": data,
        }
    }
    # OCS callers expect HTTP 200 even on logical failure; use 200 always but
    # mirror logical status in the envelope. Nextcloud's client tolerates this.
    return JSONResponse(body, status_code=200)


@router.post("/ocs/v2.php/apps/richdocuments/api/v1/federation")
async def federation_remote_wopi_token(redis: RedisDep, token: str = Form(...)) -> JSONResponse:
    """Return initiator wopi-like info for a token previously issued by the portal.

    Nextcloud's ``FederationService::getRemoteFileDetails`` calls this as part
    of WOPI ``CheckFileInfo`` to obtain ``UserFriendlyName`` (Collabora cursor
    name). Response shape mirrors a serialized ``Wopi`` entity so that
    ``Wopi::fromParams`` can hydrate it on the NC side.
    """
    info = await fed_service.lookup_initiator(redis, token)
    if info is None:
        logger.info("nc.federation_remote_wopi.not_found", token_prefix=token[:8])
        return _ocs_response(404, "Unknown initiator token", [])

    display_name = info.get("displayName", "")
    user_id = info.get("userId", "") or None

    logger.info(
        "nc.federation_remote_wopi.resolved",
        token_prefix=token[:8],
        user_id=user_id,
    )
    # Minimal Wopi-entity-shaped payload. ``setFederationFileInfo`` only reads
    # ``guestDisplayname``; the other fields are defensible defaults so that
    # ``upgradeToRemoteToken`` (if invoked downstream) does not corrupt
    # permissions.
    return _ocs_response(
        200,
        "OK",
        {
            "tokenType": _TOKEN_TYPE_INITIATOR,
            "guestDisplayname": display_name,
            "editorUid": user_id,
            "canwrite": True,
            "hideDownload": False,
        },
    )
