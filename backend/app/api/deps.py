"""FastAPI зависимости: Redis, текущий пользователь, проверка ролей."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.core.database import get_db as get_db
from app.core.logging import bind_request_context, get_logger
from app.core.security import SESSION_COOKIE_NAME, parse_jwt_claims
from app.models.user import User
from app.services import keycloak as kc_service
from app.services.session import get_session

logger = get_logger(__name__)


async def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


RedisDep = Annotated[Redis, Depends(get_redis)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Возвращает фабрику AsyncSession для кода, который должен открывать
    свои независимые сессии (например, параллельные запросы через
    ``asyncio.gather`` — см. REVIEW-3.2).

    Выделено в отдельную зависимость, чтобы тесты могли подменить фабрику
    через ``app.dependency_overrides``.
    """
    return AsyncSessionLocal


SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


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
        result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        bind_request_context(user_id=str(user.id), role=user.role, auth_source="local")
        return user

    access_token = session_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    try:
        jwks = await kc_service.get_jwks(redis)
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

    await _sync_keycloak_groups(db, redis, user, claims)

    bind_request_context(user_id=str(user.id), role=user.role, auth_source="keycloak")
    return user


async def _sync_keycloak_groups(
    db: AsyncSession,
    redis: Redis,
    user: User,
    claims: dict,
) -> None:
    """Keep ``users.keycloak_groups`` in sync with the live access-token claim.

    Group membership is only persisted during a full OIDC login (``_upsert_user``).
    Silent token refresh re-issues access tokens with up-to-date ``groups`` claims
    but never re-syncs them, so a user added to a Keycloak group mid-session would
    keep a stale group set — and any folder/KB/photo permission granted to that
    group would not apply until the next interactive login.

    Here the access token is already parsed on every request, so we treat its
    ``groups`` claim as the source of truth: on a real change we persist the new
    set and flush the per-user ACL caches so the new permissions take effect
    immediately instead of after the 5-minute TTL.
    """
    if "groups" not in claims:
        return

    new_groups = list(claims.get("groups") or [])
    current_groups = list(user.keycloak_groups or [])
    if set(new_groups) == set(current_groups):
        return

    try:
        await db.execute(update(User).where(User.id == user.id).values(keycloak_groups=new_groups))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("auth.keycloak_groups_sync_failed", user_id=str(user.id), exc_info=True)
        return

    user.keycloak_groups = new_groups

    from app.services import photos_acl
    from app.services.files_acl import (
        invalidate_file_share_user_cache,
    )
    from app.services.files_acl import (
        invalidate_user_cache as invalidate_files_user_cache,
    )
    from app.services.kb_acl import invalidate_user_cache as invalidate_kb_user_cache

    await invalidate_files_user_cache(redis, user.id)
    await invalidate_file_share_user_cache(redis, user.id)
    await invalidate_kb_user_cache(redis, user.id)
    await photos_acl.invalidate_user_cache(redis, user.id)

    logger.info(
        "auth.keycloak_groups_synced",
        user_id=str(user.id),
        group_count=len(new_groups),
    )


async def get_user_for_refresh(
    request: Request,
    redis: RedisDep,
    db: DbDep,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    """Lightweight session auth for ``POST /auth/refresh`` ONLY.

    В отличие от :func:`get_current_user` НЕ валидирует ``exp`` access-токена.
    Refresh обязан работать именно тогда, когда access-токен уже истёк (вкладка
    висела в фоне — таймер silent-refresh заморожен браузером, retry-on-401 не
    смог бы обновить токен, если бы здесь стоял ``CurrentUser``). Личность берём
    из Redis-сессии (cookie) по ``user_id``, без разбора JWT.

    Проверку ``deleted_at`` намеренно НЕ делаем здесь: её выполняет тело
    эндпоинта, которое дополнительно удаляет сессию для деактивированного
    пользователя (см. ``app/api/auth/me.py``).
    """
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session_data = await get_session(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

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

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    bind_request_context(
        user_id=str(user.id),
        role=user.role,
        auth_source=session_data.get("auth_source", "keycloak"),
    )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
RefreshUser = Annotated[User, Depends(get_user_for_refresh)]


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
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


async def require_helpdesk_agent(
    user: CurrentUser, db: DbDep
) -> User:
    """Helpdesk-agent gate: admin always passes, otherwise membership in
    ``helpdesk_agents`` is checked against the DB on every request (single
    source of truth — ТЗ §4.5). The ``is_helpdesk_agent`` flag from bootstrap
    is cosmetic only and is NOT trusted here."""
    if user.role == "admin":
        return user
    from sqlalchemy import select

    from app.models.helpdesk import HelpdeskAgent

    res = await db.execute(
        select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user.id)
    )
    if res.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a helpdesk agent",
        )
    return user


HelpdeskAgentDep = Annotated[User, Depends(require_helpdesk_agent)]
