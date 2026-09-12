"""FastAPI зависимости: Redis, текущий пользователь, проверка ролей."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.core.database import get_db as get_db
from app.core.database import get_learning_db as get_learning_db
from app.core.logging import bind_request_context, get_logger
from app.core.security import SESSION_COOKIE_NAME, parse_jwt_claims
from app.models.user import User
from app.services import keycloak as kc_service
from app.services.session import get_session

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.models.learning import LearningAccount
    from app.services.learning.participant import LearningParticipant


async def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


RedisDep = Annotated[Redis, Depends(get_redis)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
# Learning-контур: отдельный пул с DB-ролью learning_app (ТЗ learning.md §10.8);
# без LEARNING_DB_PASSWORD — тот же общий движок (dev/тесты).
LearningDbDep = Annotated[AsyncSession, Depends(get_learning_db)]


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


async def require_helpdesk_agent(user: CurrentUser, db: DbDep) -> User:
    """Helpdesk-agent gate: admin always passes, otherwise membership in
    ``helpdesk_agents`` is checked against the DB on every request (single
    source of truth — ТЗ §4.5). The ``is_helpdesk_agent`` flag from bootstrap
    is cosmetic only and is NOT trusted here."""
    if user.role == "admin":
        return user
    from sqlalchemy import select

    from app.models.helpdesk import HelpdeskAgent

    res = await db.execute(select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user.id))
    if res.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a helpdesk agent",
        )
    return user


HelpdeskAgentDep = Annotated[User, Depends(require_helpdesk_agent)]


async def require_helpdesk_module(redis: RedisDep) -> None:
    """Module gate: 404 the whole helpdesk feature when the master
    ``helpdesk.enabled`` flag is off (ТЗ §9.1). Read from ``modules.json`` via
    the shared cache, like directories."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    if not modules.helpdesk.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Helpdesk disabled")


HelpdeskModuleEnabled = Annotated[None, Depends(require_helpdesk_module)]


async def require_erp_sync_module(redis: RedisDep) -> None:
    """Module gate: 404 the whole ERP-sync feature when the master
    ``erp_sync.enabled`` flag is off. Read from ``modules.json`` via the shared
    cache (как helpdesk/directories)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    if not modules.erp_sync.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ERP sync disabled")


ErpSyncModuleEnabled = Annotated[None, Depends(require_erp_sync_module)]


async def require_directum_module(redis: RedisDep) -> None:
    """Module gate: 404 the whole Directum feature when the master
    ``directum.enabled`` flag is off. Read from ``modules.json`` via the shared
    cache (как helpdesk/erp_sync)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    if not modules.directum.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directum disabled")


DirectumModuleEnabled = Annotated[None, Depends(require_directum_module)]


# ── Модуль обучения (LMS) ────────────────────────────────────────────────────


async def require_learning_module(redis: RedisDep) -> None:
    """Мастер-переключатель ``learning.enabled`` из modules.json — 404, когда
    модуль выключен (как helpdesk/directum)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    if not modules.learning.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning disabled")


LearningModuleEnabled = Annotated[None, Depends(require_learning_module)]


async def require_approvals_module(redis: RedisDep) -> None:
    """Мастер-переключатель ``approvals.enabled`` из modules.json — 404, когда
    модуль согласования документов выключен (как helpdesk/directum)."""
    from app.core.modules_config import load_modules_shared

    modules = await load_modules_shared(redis)
    if not modules.approvals.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approvals disabled")


ApprovalsModuleEnabled = Annotated[None, Depends(require_approvals_module)]


async def require_learning_admin(user: CurrentUser, db: DbDep) -> User:
    """Методист (= админ модуля): admin портала проходит всегда, остальным
    нужно членство в ``learning_admins`` (паттерн require_helpdesk_agent)."""
    if user.role == "admin":
        return user
    from sqlalchemy import select

    from app.models.learning import LearningAdmin

    res = await db.execute(select(LearningAdmin.user_id).where(LearningAdmin.user_id == user.id))
    if res.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a learning admin",
        )
    return user


LearningAdminDep = Annotated[User, Depends(require_learning_admin)]


async def get_current_learner(
    request: Request,
    redis: RedisDep,
    # Чтение learning_accounts — только через learning-пул (§10.8): внешний
    # learner не должен обращаться к БД даже на чтение с широкими правами
    # основного движка.
    db: LearningDbDep,
    session_id: Annotated[str | None, Cookie(alias="learning_session")] = None,
) -> LearningAccount:
    """Принципал learner'а по cookie ``learning_session``. Типизирован отдельно от
    портал-пользователя: learner-cookie на штатных эндпоинтах → 401 (портальный
    resolver не знает это пространство ключей), и наоборот.
    """
    from app.models.learning import LearningAccount
    from app.services.learning.sessions import get_session_payload

    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = await get_session_payload(redis, session_id)
    if not payload or payload.get("principal_type") != "learning_account":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    account_id_raw = payload.get("account_id")
    try:
        account_id = uuid.UUID(str(account_id_raw))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc

    result = await db.execute(
        select(LearningAccount).where(
            LearningAccount.id == account_id,
            LearningAccount.deleted_at.is_(None),
            LearningAccount.status == "active",
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    bind_request_context(account_id=str(account.id), role="learner")
    return account


# Строковая форма внутри Annotated — чтобы рантайм не требовал реальный класс
# (он TYPE_CHECKING-only); для mypy резолвится через тот же импорт.
CurrentLearner = Annotated["LearningAccount", Depends(get_current_learner)]


async def get_learning_participant(
    request: Request,
    redis: RedisDep,
    # Staff-ветка резолвит users по ОСНОВНОМУ движку (граница роутера, §10.8
    # в ред. ревью #142: learning_app грантов на users не имеет).
    db: DbDep,
    # Learner-ветка читает learning_accounts через learning-пул — изоляция
    # learner-запросов от широких прав основного движка (§10.8).
    learning_db: LearningDbDep,
    learner_id: Annotated[str | None, Cookie(alias="learning_session")] = None,
    portal_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> LearningParticipant:
    """Принципал участника курса: сотрудник портала (портальная сессия) ИЛИ
    внешняя учётка (learner-cookie). Только для learning-роутов; на остальных
    эндпоинтах портала learner-cookie не признаётся (§7 ТЗ, unit-тест изоляции)."""
    from app.services.learning.participant import LearningParticipant

    if learner_id:
        account = await get_current_learner(
            request=request, redis=redis, db=learning_db, session_id=learner_id
        )
        return LearningParticipant.from_account(account)
    if portal_id:
        user = await get_current_user(request=request, redis=redis, db=db, session_id=portal_id)
        return LearningParticipant.from_user(user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


# Строковая форма внутри Annotated — как у CurrentLearner: класс TYPE_CHECKING-only.
CurrentLearningParticipant = Annotated["LearningParticipant", Depends(get_learning_participant)]
