"""Private helpers shared by auth submodules.

Extracted from the original monolithic ``app/api/auth.py`` (609 lines).
Все API-контракты (paths, methods, operationIds) сохранены — проверено
через OpenAPI snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    parse_jwt_claims,
)
from app.core.system_config import load_system_settings
from app.models.user import User
from app.services.audit import push_audit_event

logger = get_logger(__name__)
settings = get_settings()

_SSO_FAILED_URL = "/auth/error?reason=sso_failed"


def _callback_uri() -> str:
    base = load_system_settings().portal_base_url
    return f"{base}/api/v1/auth/callback"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _sso_failure_redirect(
    redis,
    request: Request,
    *,
    reason: str,
    extra: dict | None = None,
) -> RedirectResponse:
    metadata: dict = {"reason": reason}
    if extra:
        metadata.update(extra)
    await push_audit_event(
        redis,
        event_type="auth.sso_failed",
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        metadata=metadata,
    )
    return RedirectResponse(url=_SSO_FAILED_URL, status_code=status.HTTP_302_FOUND)


async def _resolve_id_token_nonce(tokens: dict, jwks, fallback_nonce) -> str | None:
    id_token_raw = tokens.get("id_token")
    if not id_token_raw:
        return fallback_nonce
    try:
        id_claims = await parse_jwt_claims(id_token_raw, jwks)
    except Exception:
        id_claims = {}
    return id_claims.get("nonce") or fallback_nonce


def _build_session_cookie_response(redirect_target: str, session_id: str) -> RedirectResponse:
    redirect = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )
    return redirect


def _nz(value):
    """Return value if it is a non-empty string/list, else None.

    Используется, чтобы отличить «JWT прислал реальное значение» от
    «клейм отсутствует / mapper не настроен / пустая строка». В последнем
    случае мы не должны затирать данные, заполненные sync'ом из Admin API.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        return value if value else None
    return value


async def _upsert_user(db, user_data: dict) -> tuple[User, bool]:
    now = datetime.now(UTC)
    email_verified = bool(user_data.pop("_email_verified", False))

    import hashlib as _hashlib

    from sqlalchemy import text as _sa_text

    _email_lock = int.from_bytes(
        _hashlib.sha256(user_data["email"].lower().encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )
    await db.execute(_sa_text("SELECT pg_advisory_xact_lock(:k)"), {"k": _email_lock})

    email_result = await db.execute(
        select(User).where(
            func.lower(User.email) == user_data["email"].lower(),
            User.deleted_at.is_(None),
        )
    )
    existing_by_email = email_result.scalar_one_or_none()
    if existing_by_email is not None and existing_by_email.keycloak_id is None:
        if not email_verified:
            logger.error(
                "auth.account_link_refused_unverified_email",
                email=existing_by_email.email,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified by IdP — account linking refused",
            )
        # Account linking: локальный аккаунт (например bootstrap-admin) получает
        # keycloak_id. Роль намеренно не перезаписывается из JWT, чтобы сохранить
        # привилегии bootstrap-admin. Логируем событие явно — критично для аудита.
        logger.warning(
            "auth.account_linked",
            user_id=str(existing_by_email.id),
            email=existing_by_email.email,
            previous_auth_source=existing_by_email.auth_source,
            previous_role=existing_by_email.role,
            new_keycloak_id=user_data["keycloak_id"],
        )
        link_values = {
            "keycloak_id": user_data["keycloak_id"],
            "full_name": func.coalesce(_nz(user_data.get("full_name")), User.full_name),
            "department": func.coalesce(_nz(user_data.get("department")), User.department),
            "position": func.coalesce(_nz(user_data.get("position")), User.position),
            "phone": func.coalesce(_nz(user_data.get("phone")), User.phone),
            "auth_source": "keycloak",
            "password_hash": None,
            "updated_at": now,
            "last_login_at": now,
        }
        if "keycloak_groups" in user_data:
            link_values["keycloak_groups"] = user_data["keycloak_groups"]
        await db.execute(
            update(User).where(User.id == existing_by_email.id).values(**link_values)
        )
        updated = await db.execute(select(User).where(User.id == existing_by_email.id))
        return updated.scalar_one(), True

    insert_values = {**user_data, "role": "reader"}
    update_set = {
        "email": user_data["email"],
        "full_name": func.coalesce(_nz(user_data.get("full_name")), User.full_name),
        "department": func.coalesce(_nz(user_data.get("department")), User.department),
        "position": func.coalesce(_nz(user_data.get("position")), User.position),
        "phone": func.coalesce(_nz(user_data.get("phone")), User.phone),
        "updated_at": now,
        "last_login_at": now,
    }
    if "keycloak_groups" in user_data:
        update_set["keycloak_groups"] = user_data["keycloak_groups"]
    stmt = (
        pg_insert(User)
        .values(
            **insert_values,
            updated_at=now,
            last_login_at=now,
        )
        .on_conflict_do_update(
            index_elements=["keycloak_id"],
            set_=update_set,
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    return result.fetchone()[0], False


def _mask_email(email: str) -> str:
    parts = email.split("@", 1)
    if len(parts) != 2 or not parts[0]:
        return "***"
    local, domain = parts
    if "." in domain:
        return local[0] + "***@" + domain[0] + "***." + domain.rsplit(".", 1)[-1]
    return local[0] + "***@" + "***"
