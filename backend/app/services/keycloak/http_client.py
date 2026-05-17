"""Singleton ``httpx.AsyncClient`` for Keycloak (lazy-init, lifespan-managed)."""

from __future__ import annotations

import httpx


def _get_kc_http_client() -> httpx.AsyncClient:
    """Return (or lazily create) the module-level shared httpx client for Keycloak."""
    from app.services import keycloak as _kc

    if _kc._KC_HTTP_CLIENT is None or _kc._KC_HTTP_CLIENT.is_closed:
        _kc._KC_HTTP_CLIENT = httpx.AsyncClient(
            timeout=_kc._KC_CLIENT_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _kc._KC_HTTP_CLIENT


async def init_kc_http_client() -> None:
    """Eagerly initialise the shared httpx client. Call during application lifespan startup."""
    from app.services import keycloak as _kc

    if _kc._KC_HTTP_CLIENT is None or _kc._KC_HTTP_CLIENT.is_closed:
        _kc._KC_HTTP_CLIENT = httpx.AsyncClient(
            timeout=_kc._KC_CLIENT_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )


async def close_kc_http_client() -> None:
    """Close the shared httpx client. Call on application shutdown."""
    from app.services import keycloak as _kc

    if _kc._KC_HTTP_CLIENT is not None and not _kc._KC_HTTP_CLIENT.is_closed:
        await _kc._KC_HTTP_CLIENT.aclose()
    _kc._KC_HTTP_CLIENT = None
