"""OIDC flow helpers: authorization/silent/logout URLs + token exchange/refresh."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlencode


def _oidc_base() -> str:
    from app.services import keycloak as _kc

    kcs = _kc._get_kc_settings()
    return f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"


def get_authorization_url(redirect_uri: str, state: str, nonce: str, code_challenge: str) -> str:
    from app.services import keycloak as _kc

    kcs = _kc._get_kc_settings()
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
    return f"{_kc._oidc_base()}/auth?{urlencode(params)}"


def get_logout_url(post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
    from app.services import keycloak as _kc

    kcs = _kc._get_kc_settings()
    params = {
        "client_id": kcs.oidc_client_id,
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return f"{_kc._oidc_base()}/logout?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    from app.services import keycloak as _kc

    kcs = await _kc._get_kc_settings_async()
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _kc._get_kc_http_client()
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
    return cast(dict[str, Any], response.json())


async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    from app.services import keycloak as _kc

    kcs = await _kc._get_kc_settings_async()
    oidc_base = f"{kcs.keycloak_url}/realms/{kcs.keycloak_realm}/protocol/openid-connect"
    client = _kc._get_kc_http_client()
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
    return cast(dict[str, Any], response.json())
