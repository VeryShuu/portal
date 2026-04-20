"""Auth endpoints: OIDC Authorization Code + PKCE flow."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    extract_user_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_session_id,
    generate_state,
    parse_jwt_claims,
)
from app.services import keycloak as kc_service
from app.services.audit import push_audit_event
from app.services.session import (
    delete_pkce_state,
    delete_session,
    get_pkce_state,
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

    await save_pkce_state(redis, state, verifier, nonce, redirect_after)

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
    user = await _upsert_user(db, user_data)

    session_id = generate_session_id()
    await save_session(redis, session_id, {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "id_token": tokens.get("id_token"),
        "user_id": str(user.id),
        "keycloak_id": user.keycloak_id,
    })

    await push_audit_event(
        redis,
        event_type="user.login",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    redirect = RedirectResponse(url=pkce.get("redirect_after", "/"), status_code=status.HTTP_302_FOUND)
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
    session_id: str | None = None,
) -> RedirectResponse:
    if session_id:
        session_data = await _get_session_from_cookie(request, redis)
        id_token_hint = (session_data or {}).get("id_token", "")
        await delete_session(redis, session_id)
        await push_audit_event(
            redis,
            event_type="user.logout",
            user_id=str(user.id),
            user_email=user.email,
            ip_address=request.client.host if request.client else None,
        )
        logout_url = kc_service.get_logout_url(
            id_token_hint=id_token_hint,
            post_logout_redirect_uri=f"{settings.portal_base_url}/auth/login",
        )
        redirect = RedirectResponse(url=logout_url, status_code=status.HTTP_302_FOUND)
    else:
        redirect = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect


@router.get("/logout", summary="GET logout (SLO front-channel)")
async def logout_get(
    redis: RedisDep,
    request: Request,
    response: Response,
) -> RedirectResponse:
    from fastapi import Cookie as CookieParam
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session_data = await get_pkce_state(redis, session_id) or await _get_session_from_cookie(request, redis)
        if session_data:
            await delete_session(redis, session_id)

    redirect = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect


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

    from app.services.session import get_session
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

    from app.services.session import save_session
    await save_session(redis, session_id, session_data)

    return {"ok": True}


async def _upsert_user(db, user_data: dict):
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    from app.models.user import User

    now = datetime.now(UTC)
    stmt = (
        insert(User)
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
    await db.commit()
    return result.fetchone()[0]


async def _get_session_from_cookie(request: Request, redis) -> dict | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    from app.services.session import get_session
    return await get_session(redis, session_id)
