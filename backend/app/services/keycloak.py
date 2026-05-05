"""Keycloak OIDC client — JWKS fetch, token exchange, introspection, user sync."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from redis.asyncio import Redis

from app.core.cache_version import get_version
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TTL = 300  # 5 min
_JWKS_VERSION_KEY = "jwks"

_settings_cache: dict[str, Any] = {}
_SETTINGS_CACHE_TTL = 60  # 1 min — cleared immediately on admin save
_SETTINGS_VERSION_KEY = "keycloak_config"

_KC_SETTINGS_FILE = Path("/data/secrets/keycloak-settings.json")
_LEGACY_KC_SETTINGS_FILE = Path("/data/branding/keycloak-settings.json")

_KC_HTTP_CLIENT: httpx.AsyncClient | None = None
_KC_CLIENT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _get_kc_http_client() -> httpx.AsyncClient:
    """Return (or lazily create) the module-level shared httpx client for Keycloak."""
    global _KC_HTTP_CLIENT
    if _KC_HTTP_CLIENT is None or _KC_HTTP_CLIENT.is_closed:
        _KC_HTTP_CLIENT = httpx.AsyncClient(
            timeout=_KC_CLIENT_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _KC_HTTP_CLIENT


def invalidate_jwks_cache() -> None:
    """Evict the in-memory JWKS cache so the next call to get_jwks() re-fetches."""
    _JWKS_CACHE.clear()


async def init_kc_http_client() -> None:
    """Eagerly initialise the shared httpx client. Call during application lifespan startup."""
    global _KC_HTTP_CLIENT
    if _KC_HTTP_CLIENT is None or _KC_HTTP_CLIENT.is_closed:
        _KC_HTTP_CLIENT = httpx.AsyncClient(
            timeout=_KC_CLIENT_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )


async def close_kc_http_client() -> None:
    """Close the shared httpx client. Call on application shutdown."""
    global _KC_HTTP_CLIENT
    if _KC_HTTP_CLIENT is not None and not _KC_HTTP_CLIENT.is_closed:
        await _KC_HTTP_CLIENT.aclose()
    _KC_HTTP_CLIENT = None


class _KCSettings:
    __slots__ = (
        "keycloak_realm",
        "keycloak_url",
        "oidc_client_id",
        "oidc_client_secret",
        "sync_client_id",
        "sync_client_secret",
    )

    def __init__(
        self,
        keycloak_url: str,
        keycloak_realm: str,
        oidc_client_id: str,
        oidc_client_secret: str,
        sync_client_id: str = "",
        sync_client_secret: str = "",
    ) -> None:
        self.keycloak_url = keycloak_url.rstrip("/")
        self.keycloak_realm = keycloak_realm
        self.oidc_client_id = oidc_client_id
        self.oidc_client_secret = oidc_client_secret
        self.sync_client_id = sync_client_id
        self.sync_client_secret = sync_client_secret


def _get_kc_settings() -> _KCSettings:
    """Load Keycloak settings from file (with fallback to .env). In-memory cached 60 s."""
    now = time.monotonic()
    if (
        _settings_cache.get("data")
        and now - _settings_cache.get("fetched_at", 0) < _SETTINGS_CACHE_TTL
    ):
        return _settings_cache["data"]

    kc_file = _KC_SETTINGS_FILE if _KC_SETTINGS_FILE.exists() else _LEGACY_KC_SETTINGS_FILE
    if kc_file.exists():
        try:
            import json

            raw = json.loads(kc_file.read_text("utf-8"))
            kc_url = raw.get("keycloak_url", "")
            kc_realm = raw.get("keycloak_realm", "")
            if kc_url and kc_realm:
                data = _KCSettings(
                    keycloak_url=kc_url,
                    keycloak_realm=kc_realm,
                    oidc_client_id=raw.get("oidc_client_id") or settings.keycloak_client_id,
                    oidc_client_secret=(
                        raw.get("oidc_client_secret") or settings.keycloak_client_secret
                    ),
                    sync_client_id=raw.get("sync_client_id", ""),
                    sync_client_secret=raw.get("sync_client_secret", ""),
                )
                _settings_cache["data"] = data
                _settings_cache["fetched_at"] = now
                return data
        except Exception:
            pass

    data = _KCSettings(
        keycloak_url=settings.keycloak_url,
        keycloak_realm=settings.keycloak_realm,
        oidc_client_id=settings.keycloak_client_id,
        oidc_client_secret=settings.keycloak_client_secret,
    )
    _settings_cache["data"] = data
    _settings_cache["fetched_at"] = now
    return data


async def _get_kc_settings_async(redis: Redis | None = None) -> _KCSettings:
    _owned = redis is None
    if _owned:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        current_version = await get_version(redis, _SETTINGS_VERSION_KEY)
    finally:
        if _owned:
            await redis.aclose()

    now = time.monotonic()
    if (
        _settings_cache.get("data")
        and _settings_cache.get("version") == current_version
        and now - _settings_cache.get("fetched_at", 0) < _SETTINGS_CACHE_TTL
    ):
        return _settings_cache["data"]

    if _settings_cache.get("version") != current_version:
        _settings_cache.clear()
    data = _get_kc_settings()
    _settings_cache["version"] = current_version
    _settings_cache["fetched_at"] = now
    _settings_cache["data"] = data
    return data


def invalidate_settings_cache() -> None:
    """Public API: drop cached Keycloak settings. Used by admin handlers after save."""
    _settings_cache.clear()


def get_kc_settings() -> _KCSettings:
    """Public wrapper — returns current Keycloak settings (file-backed, 60 s cache)."""
    return _get_kc_settings()


def _oidc_base() -> str:
    kcs = _get_kc_settings()
    return f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"


def get_authorization_url(redirect_uri: str, state: str, nonce: str, code_challenge: str) -> str:
    kcs = _get_kc_settings()
    params = {
        "response_type": "code",
        "client_id": kcs.oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{_oidc_base()}/auth?{urlencode(params)}"


def get_silent_auth_url(redirect_uri: str, state: str, nonce: str) -> str:
    kcs = _get_kc_settings()
    params = {
        "response_type": "code",
        "client_id": kcs.oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "prompt": "none",
    }
    return f"{_oidc_base()}/auth?{urlencode(params)}"


def get_logout_url(post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
    kcs = _get_kc_settings()
    params = {
        "client_id": kcs.oidc_client_id,
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return f"{_oidc_base()}/logout?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    kcs = await _get_kc_settings_async()
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _get_kc_http_client()
    response = await client.post(
        f"{oidc_base}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": kcs.oidc_client_id,
            "client_secret": kcs.oidc_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )
    response.raise_for_status()
    return response.json()


async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    kcs = await _get_kc_settings_async()
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _get_kc_http_client()
    response = await client.post(
        f"{oidc_base}/token",
        data={
            "grant_type": "refresh_token",
            "client_id": kcs.oidc_client_id,
            "client_secret": kcs.oidc_client_secret,
            "refresh_token": refresh_token,
        },
    )
    response.raise_for_status()
    return response.json()


async def get_jwks(redis: Redis | None = None) -> list[dict[str, Any]]:
    """Returns cached JWKS, refreshes every 5 minutes."""
    _owned = redis is None
    if _owned:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        current_version = await get_version(redis, _JWKS_VERSION_KEY)
    finally:
        if _owned:
            await redis.aclose()

    now = time.monotonic()
    if (
        _JWKS_CACHE.get("keys")
        and _JWKS_CACHE.get("version") == current_version
        and now - _JWKS_CACHE.get("fetched_at", 0) < _JWKS_CACHE_TTL
    ):
        return _JWKS_CACHE["keys"]

    kcs = await _get_kc_settings_async(redis if not _owned else None)
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _get_kc_http_client()
    response = await client.get(f"{oidc_base}/certs")
    response.raise_for_status()
    data = response.json()

    _JWKS_CACHE["keys"] = data["keys"]
    _JWKS_CACHE["fetched_at"] = now
    _JWKS_CACHE["version"] = current_version
    logger.info("keycloak.jwks_refreshed", key_count=len(data["keys"]))
    return data["keys"]


async def search_users(q: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search users in Keycloak by username/email/name."""
    token = await _get_directory_token()
    kcs = await _get_kc_settings_async()
    client = _get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users",
        headers={"Authorization": f"Bearer {token}"},
        params={"search": q, "max": max_results, "briefRepresentation": "false"},
    )
    response.raise_for_status()
    return response.json()


async def search_groups(q: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search groups in Keycloak by name."""
    token = await _get_directory_token()
    kcs = await _get_kc_settings_async()
    client = _get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/groups",
        headers={"Authorization": f"Bearer {token}"},
        params={"search": q, "max": max_results, "briefRepresentation": "true"},
    )
    response.raise_for_status()
    return response.json()


async def get_admin_users(page: int = 0, size: int = 100) -> list[dict[str, Any]]:
    """Fetch users from Keycloak Admin API using sync service account (view-users only)."""
    token = await _get_sync_token()
    kcs = await _get_kc_settings_async()
    client = _get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users",
        headers={"Authorization": f"Bearer {token}"},
        params={"first": page * size, "max": size, "briefRepresentation": "false"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


async def get_user_groups(user_id: str) -> list[str]:
    """Fetch group paths for a single user from Keycloak Admin API."""
    token = await _get_sync_token()
    kcs = await _get_kc_settings_async()
    client = _get_kc_http_client()
    response = await client.get(
        f"{kcs.keycloak_url}/admin/realms/{kcs.keycloak_realm}/users/{user_id}/groups",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return [g.get("path", g.get("name", "")) for g in response.json()]


async def _get_sync_token() -> str:
    """Get token using sync service account (view-users role only). Cached in Redis.

    Falls back to OIDC portal client if sync credentials are not configured.
    """
    from redis.asyncio import Redis

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        cached = await redis.get("kc:sync_token")
        if cached:
            return cached

        kcs = await _get_kc_settings_async()

        if not kcs.sync_client_id or not kcs.sync_client_secret:
            logger.warning(
                "keycloak.sync_fallback_to_oidc_client",
                note="Sync client not configured — using portal OIDC client. "
                "Configure a dedicated sync client with view-users role.",
            )
            return await _get_admin_token()

        token_url = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect/token"
        _client = _get_kc_http_client()
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

        token = data["access_token"]
        ttl = max(data.get("expires_in", 300) - 60, 30)
        await redis.set("kc:sync_token", token, ex=ttl)
        logger.info("keycloak.sync_token_refreshed", ttl=ttl)
        return token
    finally:
        await redis.aclose()


async def _get_directory_token() -> str:
    """Token for directory lookups (search_users, search_groups).

    Uses sync client if available, falls back to OIDC portal client.
    """
    kcs = await _get_kc_settings_async()
    if kcs.sync_client_id and kcs.sync_client_secret:
        return await _get_sync_token()
    return await _get_admin_token()


async def _get_admin_token() -> str:
    """Fallback: use portal OIDC client credentials for Admin API calls."""
    kcs = await _get_kc_settings_async()
    client = _get_kc_http_client()
    response = await client.post(
        f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": kcs.oidc_client_id,
            "client_secret": kcs.oidc_client_secret,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]
