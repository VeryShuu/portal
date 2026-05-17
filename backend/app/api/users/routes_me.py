"""Users API: эндпоинты текущего пользователя (/users/me)."""

from __future__ import annotations

from fastapi import Depends, Request, UploadFile
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.schemas.user import (
    PasswordChangeRequest,
    PatchPreferencesRequest,
    PatchProfileRequest,
    UserMe,
)

from . import router, users_me_service


@router.get("/me", response_model=UserMe, summary="Текущий пользователь")
async def get_me(user: CurrentUser) -> UserMe:
    return UserMe.model_validate(user)


@router.patch("/me/profile", response_model=UserMe, summary="Обновить профиль")
async def patch_my_profile(
    body: PatchProfileRequest,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_me_service.patch_my_profile(db, user, body)
    return UserMe.model_validate(updated)


@router.patch("/me/preferences", response_model=UserMe, summary="Обновить персональные настройки")
async def patch_my_preferences(
    body: PatchPreferencesRequest,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_me_service.patch_my_preferences(db, user, body)
    return UserMe.model_validate(updated)


@router.post("/me/avatar", response_model=UserMe, summary="Загрузить аватар")
async def upload_avatar(
    file: UploadFile,
    user: CurrentUser,
    db: DbDep,
) -> UserMe:
    updated = await users_me_service.upload_avatar(db, user, file)
    return UserMe.model_validate(updated)


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
    return await users_me_service.change_my_password(db, redis, request, user, body)
