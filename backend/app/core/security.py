import asyncio
import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.services.keycloak import get_jwks

settings = get_settings()

SESSION_TTL_SECONDS = 8 * 3600
SESSION_COOKIE_NAME = "portal_session"

_BCRYPT_ROUNDS = 12
DUMMY_HASH = "$2b$12$AYIUKE1io/ocfe0hko1GT.nTl9gestrHkKwLQgmoQo25bjK5UuYGi"


def _prepare_password(password: str) -> bytes:
    raw = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(raw)


def hash_password(password: str) -> str:
    """Synchronous bcrypt hash. Prefer ``hash_password_async`` in async handlers
    to avoid blocking the event loop (~200ms @ rounds=12).
    Kept for bootstrap/CLI/test contexts.
    """
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prepare_password(password), salt).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Synchronous bcrypt verify. Prefer ``verify_password_async`` in async
    handlers. Kept for test/CLI contexts.
    """
    try:
        return bcrypt.checkpw(_prepare_password(plain), hashed.encode())
    except Exception:
        return False


async def hash_password_async(password: str) -> str:
    """Offload CPU-bound bcrypt hashing to the default executor so the event
    loop stays responsive under concurrent load (see review P0-1).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Offload CPU-bound bcrypt verification to the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, verify_password, plain, hashed)


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_state() -> str:
    return secrets.token_urlsafe(16)


async def parse_jwt_claims(token: str, jwks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Parse and verify Keycloak JWT using JWKS. Returns decoded payload."""
    if jwks is None:
        jwks = await get_jwks()

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = next((k for k in jwks if k.get("kid") == kid), None)
    if key is None:
        from app.services.keycloak import _JWKS_CACHE

        _JWKS_CACHE.clear()
        jwks = await get_jwks()
        key = next((k for k in jwks if k.get("kid") == kid), None)
        if key is None:
            raise JWTError("JWK key not found after refresh")

    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=settings.keycloak_client_id,
        issuer=f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}",
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
