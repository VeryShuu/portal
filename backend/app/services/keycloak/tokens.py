"""Service-account token helpers (sync / directory / admin fallback)."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_app_settings = get_settings()


async def _get_sync_token() -> str:
    """Get token using sync service account (view-users role only). Cached in Redis.

    Falls back to OIDC portal client if sync credentials are not configured.
    """
    from app.services import keycloak as _kc

    redis = Redis.from_url(_app_settings.redis_url, decode_responses=True)
    try:
        cached = await redis.get("kc:sync_token")
        if cached:
            return str(cached)

        kcs = await _kc._get_kc_settings_async()

        if not kcs.sync_client_id or not kcs.sync_client_secret:
            logger.warning(
                "keycloak.sync_fallback_to_oidc_client",
                note="Sync client not configured — using portal OIDC client. "
                "Configure a dedicated sync client with view-users role.",
            )
            return await _kc._get_admin_token()

        token_url = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect/token"
        _client = _kc._get_kc_http_client()
        resp = await _client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": kcs.sync_client_id,
                "client_secret": kcs.sync_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        token = str(data["access_token"])
        ttl = max(data.get("expires_in", 300) - 60, 30)
        await redis.set("kc:sync_token", token, ex=ttl)
        logger.info("keycloak.sync_token_refreshed", ttl=ttl)
        return token
    finally:
        await redis.aclose()


async def _get_directory_token() -> str:
    """Token for directory lookups (``search_users``, ``search_groups``).

    Uses sync client if available, falls back to OIDC portal client.
    """
    from app.services import keycloak as _kc

    kcs = await _kc._get_kc_settings_async()
    if kcs.sync_client_id and kcs.sync_client_secret:
        return await _kc._get_sync_token()
    return await _kc._get_admin_token()


async def _get_admin_token() -> str:
    """Fallback: use portal OIDC client credentials for Admin API calls."""
    from app.services import keycloak as _kc

    kcs = await _kc._get_kc_settings_async()
    client = _kc._get_kc_http_client()
    response = await client.post(
        f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": kcs.oidc_client_id,
            "client_secret": kcs.oidc_client_secret,
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])
