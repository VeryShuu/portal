"""Локальный логин (email + пароль) и публичный конфиг аутентификации."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, select, update

from app.api.deps import DbDep, RedisDep
from app.core.config import get_settings
from app.core.limiter import email_identifier
from app.core.security import (
    DUMMY_HASH,
    LAST_AUTH_METHOD_COOKIE,
    LAST_AUTH_METHOD_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    generate_session_id,
    verify_password_async,
)
from app.models.user import User
from app.schemas.user import LocalLoginRequest
from app.services.audit import push_audit_event
from app.services.session import delete_session, save_session

from ._helpers import _mask_email, logger

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post(
    "/local/login",
    summary="Локальный вход по email + паролю",
    dependencies=[
        Depends(RateLimiter(times=5, minutes=15)),
        Depends(RateLimiter(times=10, minutes=15, identifier=email_identifier)),
    ],
)
async def local_login(
    body: LocalLoginRequest,
    redis: RedisDep,
    db: DbDep,
    request: Request,
    response: Response,
) -> JSONResponse:
    if not settings.local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local authentication is disabled",
        )

    result = await db.execute(
        select(User).where(func.lower(User.email) == body.email.lower(), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    candidate_hash = (
        user.password_hash
        if (user and user.auth_source == "local" and user.password_hash)
        else DUMMY_HASH
    )
    password_ok = await verify_password_async(body.password, candidate_hash)

    if not user or user.auth_source != "local" or not user.password_hash or not password_ok:
        logger.info("auth.local_login_denied", email=_mask_email(body.email))
        logger.debug(
            "auth.local_login_denied.detail",
            reason=(
                "no_user"
                if not user
                else ("wrong_source" if user.auth_source != "local" else "bad_password")
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    now = datetime.now(UTC)
    await db.execute(update(User).where(User.id == user.id).values(last_login_at=now))
    await db.commit()

    old_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if old_session_id:
        await delete_session(redis, old_session_id)

    session_id = generate_session_id()
    await save_session(
        redis,
        session_id,
        {
            "user_id": str(user.id),
            "auth_source": "local",
        },
    )

    await push_audit_event(
        redis,
        event_type="auth.login",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        metadata={"source": "local"},
    )

    logger.info("auth.local_login", user_id=str(user.id), email=_mask_email(user.email))

    resp = JSONResponse({"ok": True, "user_id": str(user.id)})
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )
    # ADR-036 п.7: бэкенд-управляемый маркер способа входа. Фронт читает его на
    # холодном старте, чтобы при истечении Redis-сессии уйти на /auth/local, а
    # не на Keycloak SSO. Переживает logout (см. logout.py — не удаляется).
    resp.set_cookie(
        key=LAST_AUTH_METHOD_COOKIE,
        value="local",
        max_age=LAST_AUTH_METHOD_TTL_SECONDS,
        httponly=False,
        secure=get_settings().is_production,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/config", summary="Конфигурация аутентификации (без авторизации)")
async def auth_config(
    request: Request,
) -> dict:
    # ADR-036 п.7: `last_auth_method` даёт фронту на холодном старте знать тип
    # последнего входа — куда редиректить при истечении сессии. Читается из
    # долгоживущей cookie `portal_auth_method`, которую бэкенд ставит на
    # login/callback. Отсутствует (None) — у нового устройства/чистого браузера
    # нет истории входа, фронт остаётся на дефолте keycloak.
    raw = request.cookies.get(LAST_AUTH_METHOD_COOKIE)
    last_auth_method: str | None = raw if raw in ("local", "keycloak") else None
    return {
        "local_auth_enabled": settings.local_auth_enabled,
        "keycloak_enabled": True,
        "last_auth_method": last_auth_method,
    }
