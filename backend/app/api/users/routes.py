"""Users API: справочник сотрудников, профиль, синхронизация."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi_limiter.depends import RateLimiter

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.schemas.user import (
    AdminPatchProfileRequest,
    LocalUserCreateRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    PatchPreferencesRequest,
    PatchProfileRequest,
    PatchRoleRequest,
    UserList,
    UserMe,
    UserPublic,
)

from . import users_repo, users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList, summary="Список сотрудников")
async def list_users(
    db: DbDep,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> UserList:
    total = await users_repo.count_users(db, q=q, department=department)
    items = await users_repo.list_users_page(
        db, q=q, department=department, page=page, page_size=page_size
    )
    return UserList(
        items=[UserPublic.model_validate(u) for u in items],
        total=total,
    )


@router.get("/me", response_model=UserMe, summary="Текущий пользователь")
async def get_me(user: CurrentUser) -> UserMe:
    return UserMe.model_validate(user)


@router.get("/{user_id}", response_model=UserPublic, summary="Профиль сотрудника")
async def get_user(
    user_id: uuid.UUID,
    db: DbDep,
    _: CurrentUser,
) -> UserPublic:
    user = await users_repo.fetch_active_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(user)


@router.patch("/me/profile", response_model=UserMe, summary="Обновить профиль")
async def patch_my_profile(
    body: PatchProfileRequest,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_service.patch_my_profile(db, user, body)
    return UserMe.model_validate(updated)


@router.patch("/me/preferences", response_model=UserMe, summary="Обновить персональные настройки")
async def patch_my_preferences(
    body: PatchPreferencesRequest,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_service.patch_my_preferences(db, user, body)
    return UserMe.model_validate(updated)


@router.post("/me/avatar", response_model=UserMe, summary="Загрузить аватар")
async def upload_avatar(
    file: UploadFile,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_service.upload_avatar(db, user, file)
    return UserMe.model_validate(updated)


@router.post("/admin/sync", summary="Синхронизировать пользователей из Keycloak")
async def sync_users_from_keycloak(
    request: Request,
    admin: AdminDep,
    redis: RedisDep,
) -> dict:
    return await users_service.enqueue_keycloak_sync(request, admin, redis)


@router.patch("/admin/{user_id}/role", summary="Сменить роль пользователя")
async def change_user_role(
    user_id: uuid.UUID,
    body: PatchRoleRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    updated = await users_service.change_user_role(db, redis, admin, user_id, body)
    return UserPublic.model_validate(updated)


@router.post("/admin/local", response_model=UserPublic, summary="Создать локального пользователя")
async def create_local_user(
    body: LocalUserCreateRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    created = await users_service.create_local_user(db, redis, admin, body)
    return UserPublic.model_validate(created)


@router.get(
    "/admin/{user_id}/groups",
    summary="Группы Keycloak пользователя (только для админа)",
)
async def admin_get_user_groups(
    user_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
) -> dict:
    return await users_service.get_user_groups(db, user_id)


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
    updated = await users_service.admin_patch_profile(db, redis, admin, user_id, body)
    return UserPublic.model_validate(updated)


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
    await users_service.delete_user(db, redis, admin, user_id)


@router.patch(
    "/me/password",
    summary="Сменить пароль (только для локальных пользователей)",
    dependencies=[Depends(RateLimiter(times=10, minutes=15))],
)
async def change_my_password(
    body: PasswordChangeRequest,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> dict:
    return await users_service.change_my_password(db, redis, request, user, body)


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
    return await users_service.reset_user_password(db, redis, admin, user_id, body)
