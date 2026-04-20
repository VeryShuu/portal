import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

SESSION_TTL_SECONDS = 8 * 3600
SESSION_COOKIE_NAME = "portal_session"


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_pkce_challenge(verifier: str) -> str:
    import base64

    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_state() -> str:
    return secrets.token_urlsafe(16)


def parse_jwt_claims(token: str, jwks: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse and verify Keycloak JWT using JWKS. Returns decoded payload."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = next((k for k in jwks if k.get("kid") == kid), None)
    if key is None:
        raise JWTError(f"JWK key not found: kid={kid}")
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=settings.keycloak_client_id,
        options={"verify_exp": True},
    )


def extract_user_data(claims: dict[str, Any]) -> dict[str, Any]:
    """Map Keycloak JWT claims → portal user fields."""
    roles = claims.get("realm_access", {}).get("roles", [])
    portal_role = "reader"
    for r in ("admin", "editor"):
        if r in roles:
            portal_role = r
            break

    return {
        "keycloak_id": claims["sub"],
        "email": claims.get("email", ""),
        "full_name": claims.get("name", claims.get("preferred_username", "")),
        "department": claims.get("department"),
        "position": claims.get("job_title"),
        "phone": claims.get("phone"),
        "role": portal_role,
    }
