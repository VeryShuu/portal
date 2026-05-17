"""Эндпоинты сессии: ``/auth/me`` и ``/auth/refresh``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, RedisDep
from app.core.config import get_settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    generate_session_id,
)
from app.services import keycloak as kc_service
from app.services.session import delete_session, get_session, save_session

from ._helpers import logger

router = APIRouter(prefix="/auth", tags=["auth"])


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
        "auth_source": user.auth_source,
    }


@router.post(
    "/refresh",
    summary="Refresh access token silently",
    dependencies=[Depends(RateLimiter(times=30, minutes=1))],
)
async def refresh_token_endpoint(
    user: CurrentUser,
    redis: RedisDep,
    request: Request,
    response: Response,
) -> dict:
    old_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not old_session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No session")

    if user.deleted_at is not None:
        await delete_session(redis, old_session_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    session_data = await get_session(redis, old_session_id)
    if not session_data or not session_data.get("refresh_token"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    try:
        tokens = await kc_service.refresh_tokens(session_data["refresh_token"])
    except Exception as exc:
        logger.warning(
            "auth.refresh_failed",
            user_id=str(user.id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh failed",
        ) from exc

    session_data["access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        session_data["refresh_token"] = tokens["refresh_token"]

    new_session_id = generate_session_id()
    await save_session(redis, new_session_id, session_data)
    await delete_session(redis, old_session_id)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )

    return {"ok": True}
