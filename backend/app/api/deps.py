"""FastAPI зависимости: Redis, текущий пользователь, проверка ролей."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import bind_request_context, get_logger
from app.core.security import SESSION_COOKIE_NAME, parse_jwt_claims
from app.models.user import User
from app.services import keycloak as kc_service
from app.services.session import get_session

logger = get_logger(__name__)


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    redis: RedisDep,
    db: DbDep,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session_data = await get_session(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    auth_source = session_data.get("auth_source", "keycloak")

    if auth_source == "local":
        user_id_str = session_data.get("user_id")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session",
            ) from exc
        result = await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        bind_request_context(user_id=str(user.id), role=user.role, auth_source="local")
        return user

    access_token = session_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    try:
        jwks = await kc_service.get_jwks()
        claims = await parse_jwt_claims(access_token, jwks)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired",
        ) from exc

    result = await db.execute(
        select(User).where(
            User.keycloak_id == claims["sub"],
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    bind_request_context(user_id=str(user.id), role=user.role, auth_source="keycloak")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: str):
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check


def require_editor(user: Annotated[User, Depends(require_role("editor", "admin"))]) -> User:
    return user


def require_admin(user: Annotated[User, Depends(require_role("admin"))]) -> User:
    return user


EditorDep = Annotated[User, Depends(require_editor)]
AdminDep = Annotated[User, Depends(require_admin)]
