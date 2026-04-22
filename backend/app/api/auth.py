"""Auth endpoints: OIDC Authorization Code + PKCE flow + local email/password."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redirects import safe_redirect
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    extract_user_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_session_id,
    generate_state,
    hash_password,
    parse_jwt_claims,
    verify_password,
)
from app.models.user import User
from app.schemas.user import LocalLoginRequest
from app.services import keycloak as kc_service
from app.services.audit import push_audit_event
from app.services.session import (
    delete_pkce_state,
    delete_session,
    get_pkce_state,
    get_session,
    get_session_from_request,
    save_pkce_state,
    save_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = get_logger(__name__)


def _callback_uri() -> str:
    return f"{settings.portal_base_url}/auth/callback"


@router.get("/login", summary="Redirect to Keycloak login")
async def login(
    redis: RedisDep,
    redirect_after: str = Query(default="/", alias="redirect"),
) -> RedirectResponse:
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    state = generate_state()
    nonce = generate_state()

    # P0-3: validate redirect_after to block open-redirect.
    safe_target = safe_redirect(redirect_after, default="/")
    await save_pkce_state(redis, state, verifier, nonce, safe_target)

    url = kc_service.get_authorization_url(
        redirect_uri=_callback_uri(),
        state=state,
        nonce=nonce,
        code_challenge=challenge,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback", summary="OIDC callback — exchange code for session")
async def callback(
    code: str,
    state: str,
    redis: RedisDep,
    db: DbDep,
    request: Request,
    response: Response,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        logger.warning("auth.callback_error", error=error)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"OIDC error: {error}")

    pkce = await get_pkce_state(redis, state)
    if not pkce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state")

    await delete_pkce_state(redis, state)

    try:
        tokens = await kc_service.exchange_code_for_tokens(
            code=code,
            redirect_uri=_callback_uri(),
            code_verifier=pkce["verifier"],
        )
    except Exception as exc:
        logger.error("auth.token_exchange_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token exchange failed")

    jwks = await kc_service.get_jwks()
    try:
        claims = parse_jwt_claims(tokens["access_token"], jwks)
    except Exception as exc:
        logger.error("auth.jwt_parse_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token validation failed")

    user_data = extract_user_data(claims)
    # P1-16: pass email_verified through so account-linking can require it.
    user_data["_email_verified"] = bool(claims.get("email_verified"))
    user = await _upsert_user(db, user_data)
    await db.commit()

    session_id = generate_session_id()
    await save_session(redis, session_id, {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "id_token": tokens.get("id_token"),
        "user_id": str(user.id),
        "keycloak_id": user.keycloak_id,
        "auth_source": "keycloak",
    })

    await push_audit_event(
        redis,
        event_type="auth.login",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        metadata={"source": "keycloak"},
    )

    redirect_target = safe_redirect(pkce.get("redirect_after"), default="/")
    redirect = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    return redirect


@router.post("/logout", summary="Logout — destroy session + SLO")
async def logout(
    user: CurrentUser,
    redis: RedisDep,
    request: Request,
) -> RedirectResponse:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = await get_session_from_request(request, redis)
    auth_source = (session_data or {}).get("auth_source", "keycloak")

    if session_id:
        await delete_session(redis, session_id)

    await push_audit_event(
        redis,
        event_type="auth.logout",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        metadata={"source": auth_source},
    )

    if auth_source == "local":
        redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    else:
        id_token_hint = (session_data or {}).get("id_token", "")
        logout_url = kc_service.get_logout_url(
            id_token_hint=id_token_hint,
            post_logout_redirect_uri=f"{settings.portal_base_url}/login",
        )
        redirect = RedirectResponse(url=logout_url, status_code=status.HTTP_302_FOUND)

    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect


@router.get("/logout", summary="GET logout (SLO front-channel)")
async def logout_get(
    redis: RedisDep,
    request: Request,
    response: Response,
) -> RedirectResponse:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await delete_session(redis, session_id)

    redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect


@router.post(
    "/local/login",
    summary="Локальный вход по email + паролю",
    dependencies=[Depends(RateLimiter(times=5, minutes=15))],
)
async def local_login(
    body: LocalLoginRequest,
    redis: RedisDep,
    db: DbDep,
    request: Request,
    response: Response,
) -> JSONResponse:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local authentication is disabled")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Унифицированный 401 — не раскрываем факт существования email и его auth_source.
    # Keycloak-аккаунты тоже получают 401 (без подсказки «use SSO»), чтобы убрать
    # user enumeration через различие кодов/сообщений.
    if (
        not user
        or user.auth_source != "local"
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        # Лёгкое логирование для SOC — без утечки наружу.
        logger.info(
            "auth.local_login_denied",
            email=body.email,
            reason="no_user" if not user else ("wrong_source" if user.auth_source != "local" else "bad_password"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    now = datetime.now(UTC)
    await db.execute(update(User).where(User.id == user.id).values(last_login_at=now))
    await db.commit()

    session_id = generate_session_id()
    await save_session(redis, session_id, {
        "user_id": str(user.id),
        "auth_source": "local",
    })

    await push_audit_event(
        redis,
        event_type="auth.login",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        metadata={"source": "local"},
    )

    logger.info("auth.local_login", user_id=str(user.id), email=user.email)

    resp = JSONResponse({"ok": True, "user_id": str(user.id)})
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/me", summary="Current user info from session")
async def me(user: CurrentUser) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "department": user.department,
        "position": user.position,
        "phone": user.phone,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "presence_status": user.presence_status,
        "notify_email": user.notify_email,
        "notify_inapp": user.notify_inapp,
        "lang": user.lang,
        "preferences": user.preferences,
    }


@router.post("/refresh", summary="Refresh access token silently")
async def refresh_token_endpoint(
    user: CurrentUser,
    redis: RedisDep,
    request: Request,
) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No session")

    session_data = await get_session(redis, session_id)
    if not session_data or not session_data.get("refresh_token"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    try:
        tokens = await kc_service.refresh_tokens(session_data["refresh_token"])
    except Exception as exc:
        logger.warning("auth.refresh_failed", user_id=str(user.id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh failed")

    session_data["access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        session_data["refresh_token"] = tokens["refresh_token"]

    await save_session(redis, session_id, session_data)

    return {"ok": True}


async def _upsert_user(db, user_data: dict) -> User:
    now = datetime.now(UTC)
    # P1-16: extract email_verified from extra payload (do not persist it as a column).
    email_verified = bool(user_data.pop("_email_verified", False))

    email_result = await db.execute(select(User).where(User.email == user_data["email"]))
    existing_by_email = email_result.scalar_one_or_none()
    if existing_by_email is not None and existing_by_email.keycloak_id is None:
        # P1-16: refuse account-linking unless Keycloak attests email is verified.
        # Without this gate an attacker who registers an unverified Keycloak account
        # under bootstrap-admin's email could hijack the local admin user.
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
        await db.execute(
            update(User)
            .where(User.id == existing_by_email.id)
            .values(
                keycloak_id=user_data["keycloak_id"],
                full_name=user_data["full_name"],
                department=user_data.get("department"),
                position=user_data.get("position"),
                phone=user_data.get("phone"),
                auth_source="keycloak",
                password_hash=None,
                updated_at=now,
                last_login_at=now,
            )
        )
        updated = await db.execute(select(User).where(User.id == existing_by_email.id))
        return updated.scalar_one()

    stmt = (
        pg_insert(User)
        .values(
            **user_data,
            updated_at=now,
            last_login_at=now,
        )
        .on_conflict_do_update(
            index_elements=["keycloak_id"],
            set_={
                "email": user_data["email"],
                "full_name": user_data["full_name"],
                "department": user_data.get("department"),
                "position": user_data.get("position"),
                "phone": user_data.get("phone"),
                "updated_at": now,
                "last_login_at": now,
            },
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    return result.fetchone()[0]


@router.get("/config", summary="Конфигурация аутентификации (без авторизации)")
async def auth_config() -> dict:
    return {
        "local_auth_enabled": settings.local_auth_enabled,
        "keycloak_enabled": True,
    }
