"""Users API: административные эндпоинты (/users/admin/*)."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import Depends, Request, status
from fastapi_limiter.depends import RateLimiter

from app.api.deps import AdminDep, DbDep, RedisDep
from app.schemas.user import (
    AdminPatchProfileRequest,
    LocalUserCreateRequest,
    PasswordResetRequest,
    PatchRoleRequest,
    UserPublic,
)

from . import router, users_admin_service


@router.post("/admin/sync", summary="Синхронизировать пользователей из Keycloak")
async def sync_users_from_keycloak(
    request: Request,
    admin: AdminDep,
    redis: RedisDep,
) -> dict:
    return await users_admin_service.enqueue_keycloak_sync(request, admin, redis)


@router.patch("/admin/{user_id}/role", summary="Сменить роль пользователя")
async def change_user_role(
    user_id: uuid.UUID,
    body: PatchRoleRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    updated = await users_admin_service.change_user_role(db, redis, admin, user_id, body)
    return cast(UserPublic, UserPublic.model_validate(updated))


@router.post("/admin/local", response_model=UserPublic, summary="Создать локального пользователя")
async def create_local_user(
    body: LocalUserCreateRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    created = await users_admin_service.create_local_user(db, redis, admin, body)
    return cast(UserPublic, UserPublic.model_validate(created))


@router.get(
    "/admin/{user_id}/groups",
    summary="Группы Keycloak пользователя (только для админа)",
)
async def admin_get_user_groups(
    user_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
) -> dict:
    return await users_admin_service.get_user_groups(db, user_id)


@router.patch(
    "/admin/{user_id}/profile",
    response_model=UserPublic,
    summary="Редактировать профиль локального пользователя",
)
async def admin_patch_user_profile(
    user_id: uuid.UUID,
    body: AdminPatchProfileRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    updated = await users_admin_service.admin_patch_profile(db, redis, admin, user_id, body)
    return cast(UserPublic, UserPublic.model_validate(updated))


@router.delete(
    "/admin/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя",
)
async def delete_user(
    user_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    await users_admin_service.delete_user(db, redis, admin, user_id)


@router.patch(
    "/admin/{user_id}/password",
    summary="Сбросить пароль (только admin, только локальные)",
    dependencies=[Depends(RateLimiter(times=20, minutes=15))],
)
async def reset_user_password(
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> dict:
    return await users_admin_service.reset_user_password(db, redis, admin, user_id, body)
