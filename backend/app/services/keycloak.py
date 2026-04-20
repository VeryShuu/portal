"""Keycloak OIDC client — JWKS fetch, token exchange, introspection, user sync."""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TTL = 300  # 5 min


def _oidc_base() -> str:
    return f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect"


def get_authorization_url(redirect_uri: str, state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.keycloak_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_oidc_base()}/auth?{query}"


def get_silent_auth_url(redirect_uri: str, state: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.keycloak_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "prompt": "none",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_oidc_base()}/auth?{query}"


def get_logout_url(id_token_hint: str, post_logout_redirect_uri: str) -> str:
    params = {
        "client_id": settings.keycloak_client_id,
        "id_token_hint": id_token_hint,
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_oidc_base()}/logout?{query}"


async def exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{_oidc_base()}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{_oidc_base()}/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_jwks() -> list[dict[str, Any]]:
    """Returns cached JWKS, refreshes every 5 minutes."""
    now = time.monotonic()
    if _JWKS_CACHE.get("keys") and now - _JWKS_CACHE.get("fetched_at", 0) < _JWKS_CACHE_TTL:
        return _JWKS_CACHE["keys"]

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{_oidc_base()}/certs")
        response.raise_for_status()
        data = response.json()

    _JWKS_CACHE["keys"] = data["keys"]
    _JWKS_CACHE["fetched_at"] = now
    logger.info("keycloak.jwks_refreshed", key_count=len(data["keys"]))
    return data["keys"]


async def get_admin_users(page: int = 0, size: int = 100) -> list[dict[str, Any]]:
    """Fetch users from Keycloak Admin API (uses client_credentials)."""
    token = await _get_admin_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}/users",
            headers={"Authorization": f"Bearer {token}"},
            params={"first": page * size, "max": size, "briefRepresentation": "false"},
        )
        response.raise_for_status()
        return response.json()


async def _get_admin_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]
