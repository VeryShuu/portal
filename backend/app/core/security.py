import asyncio
import base64
import hashlib
import secrets
import time
from datetime import timedelta
from typing import Any

import bcrypt
import jwt as pyjwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from app.core.config import get_settings

_OPTIONAL_PROFILE_CLAIMS = ("phone", "department", "job_title")

settings = get_settings()

_JWKS_LAST_FORCE_REFRESH: float = 0.0
_JWKS_MIN_REFRESH_INTERVAL = 30.0

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
    loop stays responsive under concurrent load.
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
    import json

    from app.services.keycloak import get_jwks, get_kc_settings, invalidate_jwks_cache

    if jwks is None:
        jwks = await get_jwks()

    header = pyjwt.get_unverified_header(token)
    kid = header.get("kid")
    alg = header.get("alg", "RS256")

    if alg not in ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512"):
        raise pyjwt.exceptions.InvalidAlgorithmError(f"Unsupported algorithm: {alg!r}")

    key_data = next((k for k in jwks if k.get("kid") == kid), None)
    if key_data is None:
        global _JWKS_LAST_FORCE_REFRESH
        now = time.monotonic()
        if now - _JWKS_LAST_FORCE_REFRESH >= _JWKS_MIN_REFRESH_INTERVAL:
            _JWKS_LAST_FORCE_REFRESH = now
            invalidate_jwks_cache()
            jwks = await get_jwks()
            key_data = next((k for k in jwks if k.get("kid") == kid), None)
        if key_data is None:
            raise pyjwt.exceptions.InvalidKeyError("JWK key not found after refresh")

    if alg.startswith(("RS", "PS")):
        public_key: Any = RSAAlgorithm.from_jwk(json.dumps(key_data))
    elif alg.startswith("ES"):
        public_key = ECAlgorithm.from_jwk(json.dumps(key_data))
    else:
        raise pyjwt.exceptions.InvalidAlgorithmError(f"Unsupported algorithm: {alg!r}")

    kcs = get_kc_settings()
    claims = pyjwt.decode(
        token,
        public_key,
        algorithms=[alg],
        audience=kcs.oidc_client_id,
        issuer=f"{kcs.keycloak_url.rstrip('/')}/realms/{kcs.keycloak_realm}",
        options={"verify_exp": True},
        leeway=timedelta(seconds=30),
    )

    azp = claims.get("azp")
    if azp and azp != kcs.oidc_client_id:
        raise pyjwt.exceptions.InvalidTokenError(
            f"azp mismatch: expected {kcs.oidc_client_id!r}, got {azp!r}"
        )

    return claims


def extract_user_data(claims: dict[str, Any]) -> dict[str, Any]:
    """Map Keycloak JWT claims → portal user fields.

    Информацию о незаполненных опциональных claims (phone/department/job_title)
    возвращает в поле ``_missing_profile_claims`` (список) — вызывающий код сам
    решает, как её логировать. На sync-цикле (cron из worker) per-user лог
    раздувает output на N пользователей за каждый прогон, поэтому sync агрегирует
    его в одну запись; при интерактивном логине (OIDC callback) per-user лог
    уместен — его emit'ит вызывающий код.
    """
    roles = claims.get("realm_access", {}).get("roles", [])
    portal_role = "reader"
    for r in ("admin", "editor"):
        if r in roles:
            portal_role = r
            break

    groups: list[str] = claims.get("groups") or []

    missing = [c for c in _OPTIONAL_PROFILE_CLAIMS if not claims.get(c)]

    sub = claims.get("sub")
    if not sub:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    full_name = (claims.get("name") or claims.get("preferred_username") or "").strip()

    data: dict[str, Any] = {
        "keycloak_id": sub,
        "email": claims.get("email", ""),
        "full_name": full_name,
        "department": claims.get("department"),
        "position": claims.get("job_title"),
        "phone": claims.get("phone"),
        "role": portal_role,
        # Служебное поле: список незаполненных опциональных claims. Не
        # сохраняется в БД — используется только вызывающим кодом для лога.
        "_missing_profile_claims": missing,
    }
    if "groups" in claims:
        data["keycloak_groups"] = groups
    return data
