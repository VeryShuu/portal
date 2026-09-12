"""JWKS retrieval + caching."""

from __future__ import annotations

import time
from typing import Any, cast

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

from . import _state

logger = get_logger(__name__)
_app_settings = get_settings()


def invalidate_jwks_cache() -> None:
    """Evict the in-memory JWKS cache so the next call to get_jwks() re-fetches."""
    _state._JWKS_CACHE.clear()


async def get_jwks(redis: Redis | None = None) -> list[dict[str, Any]]:
    """Returns cached JWKS, refreshes every 5 minutes."""
    from app.services import keycloak as _kc

    _owned = redis is None
    if _owned:
        redis = Redis.from_url(_app_settings.redis_url, decode_responses=True)
    assert redis is not None
    try:
        current_version = await _kc.get_version(redis, _state._JWKS_VERSION_KEY)
    finally:
        if _owned:
            await redis.aclose()

    now = time.monotonic()
    if (
        _state._JWKS_CACHE.get("keys")
        and _state._JWKS_CACHE.get("version") == current_version
        and now - _state._JWKS_CACHE.get("fetched_at", 0) < _state._JWKS_CACHE_TTL
    ):
        return cast(list[dict[str, Any]], _state._JWKS_CACHE["keys"])

    kcs = await _kc._get_kc_settings_async(redis if not _owned else None)
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _kc._get_kc_http_client()
    response = await client.get(f"{oidc_base}/certs")
    response.raise_for_status()
    data = response.json()

    keys: list[dict[str, Any]] = cast(list[dict[str, Any]], data["keys"])
    _state._JWKS_CACHE["keys"] = keys
    _state._JWKS_CACHE["fetched_at"] = now
    _state._JWKS_CACHE["version"] = current_version
    logger.info("keycloak.jwks_refreshed", key_count=len(keys))
    return keys
