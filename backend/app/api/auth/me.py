"""Эндпоинты сессии: ``/auth/me`` и ``/auth/refresh``."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, RedisDep, RefreshUser
from app.core.config import get_settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
)
from app.services import keycloak as kc_service
from app.services.session import (
    REFRESH_COALESCE_WINDOW_S,
    acquire_refresh_lock,
    delete_session,
    get_session,
    release_refresh_lock,
    save_session,
)

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
    user: RefreshUser,
    redis: RedisDep,
    request: Request,
    response: Response,
) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No session")

    if user.deleted_at is not None:
        await delete_session(redis, session_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    # Сериализуем параллельные refresh из одного браузера: пока «лидер»
    # обновляет токены, остальные ждут и затем читают уже свежий refresh_token,
    # вместо того чтобы слать в Keycloak уже отозванный (→ invalid_grant → 401).
    lock_token = await acquire_refresh_lock(redis, session_id)
    try:
        session_data = await get_session(redis, session_id)
        if not session_data or not session_data.get("refresh_token"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

        # Коалесинг мультитаб-бурста: если соседняя вкладка обновила токены
        # только что, наш access_token заведомо ещё жив — не дёргаем Keycloak
        # повторно и не ротируем refresh-токен лишний раз.
        refreshed_at = session_data.get("refreshed_at")
        if refreshed_at and (time.time() - float(refreshed_at)) < REFRESH_COALESCE_WINDOW_S:
            _set_session_cookie(response, session_id)
            return {"ok": True}

        prev_access = session_data.get("access_token")
        try:
            tokens = await kc_service.refresh_tokens(session_data["refresh_token"])
        except Exception as exc:
            # Возможная гонка ротации refresh-токена: соседний поток уже обновил
            # сессию (lock мог истечь). Если access_token изменился — считаем
            # refresh успешным и не выбиваем пользователя.
            latest = await get_session(redis, session_id)
            if latest and latest.get("access_token") and latest.get("access_token") != prev_access:
                _set_session_cookie(response, session_id)
                return {"ok": True}
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
        session_data["refreshed_at"] = time.time()

        # Обновляем токены in-place под тем же session_id — cookie не меняется,
        # поэтому параллельные вкладки не теряют свою сессию.
        await save_session(redis, session_id, session_data)
    finally:
        if lock_token:
            await release_refresh_lock(redis, session_id, lock_token)

    _set_session_cookie(response, session_id)
    return {"ok": True}


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )
