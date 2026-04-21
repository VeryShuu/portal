"""Users API: справочник сотрудников, профиль, синхронизация."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import (
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

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()
logger = get_logger(__name__)

AVATARS_DIR = Path("/data/avatars")
ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB


@router.get("", response_model=UserList, summary="Список сотрудников")
async def list_users(
    db: DbDep,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> UserList:
    stmt = select(User)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            User.full_name.ilike(pattern) | User.email.ilike(pattern)
        )
    if department:
        stmt = stmt.where(User.department == department)

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()

    stmt = stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return UserList(items=list(users), total=total)


@router.get("/me", response_model=UserMe, summary="Текущий пользователь")
async def get_me(user: CurrentUser) -> User:
    return user


@router.get("/{user_id}", response_model=UserPublic, summary="Профиль сотрудника")
async def get_user(
    user_id: uuid.UUID,
    db: DbDep,
    _: CurrentUser,
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/me/profile", response_model=UserMe, summary="Обновить профиль")
async def patch_my_profile(
    body: PatchProfileRequest,
    user: CurrentUser,
    db: DbDep,
) -> User:
    updates: dict = {}

    if body.presence_status is not None:
        if body.presence_status not in ("office", "remote", "vacation"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid presence_status")
        updates["presence_status"] = body.presence_status

    if body.lang is not None:
        if body.lang not in ("ru", "en"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid lang")
        updates["lang"] = body.lang

    if body.notify_email is not None:
        updates["notify_email"] = body.notify_email

    if body.notify_inapp is not None:
        updates["notify_inapp"] = body.notify_inapp

    if not updates:
        return user

    await db.execute(update(User).where(User.id == user.id).values(**updates))
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/me/preferences", response_model=UserMe, summary="Обновить персональные настройки")
async def patch_my_preferences(
    body: PatchPreferencesRequest,
    user: CurrentUser,
    db: DbDep,
) -> User:
    prefs = dict(user.preferences or {})

    if body.hidden_link_ids is not None:
        prefs["hidden_link_ids"] = body.hidden_link_ids

    await db.execute(update(User).where(User.id == user.id).values(preferences=prefs))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserMe, summary="Загрузить аватар")
async def upload_avatar(
    file: UploadFile,
    user: CurrentUser,
    db: DbDep,
) -> User:
    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported image type")

    content = await file.read()
    if len(content) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Avatar too large (max 5 MB)")

    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    filename = f"{user.id}.{ext}"
    file_path = AVATARS_DIR / filename

    with open(file_path, "wb") as f:
        f.write(content)

    avatar_url = f"/media/avatars/{filename}"
    await db.execute(update(User).where(User.id == user.id).values(avatar_url=avatar_url))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/admin/sync", summary="Синхронизировать пользователей из Keycloak")
async def sync_users_from_keycloak(
    _: AdminDep,
    redis: RedisDep,
) -> dict:
    from arq import create_pool
    from arq.connections import RedisSettings
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await pool.enqueue_job("app.worker.tasks.users.sync_users_from_keycloak")
    await pool.aclose()
    return {"job_id": job.job_id if job else None, "status": "queued"}


@router.patch("/admin/{user_id}/role", summary="Сменить роль пользователя")
async def change_user_role(
    user_id: uuid.UUID,
    body: PatchRoleRequest,
    admin: AdminDep,
    db: DbDep,
) -> UserPublic:
    if body.role not in ("reader", "editor", "admin"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.execute(update(User).where(User.id == user_id).values(role=body.role))
    await db.commit()
    await db.refresh(user)

    logger.info("admin.role_changed", target_user_id=str(user_id), new_role=body.role, by=str(admin.id))
    return user


@router.post("/admin/local", response_model=UserPublic, summary="Создать локального пользователя")
async def create_local_user(
    body: LocalUserCreateRequest,
    admin: AdminDep,
    db: DbDep,
) -> User:
    from app.core.config import get_settings as _gs
    if not _gs().local_auth_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local authentication is disabled")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    from app.core.security import hash_password
    from datetime import UTC, datetime
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(UTC)
    stmt = pg_insert(User).values(
        email=body.email,
        full_name=body.full_name,
        auth_source="local",
        password_hash=hash_password(body.password),
        role=body.role,
        updated_at=now,
    ).returning(User)
    result = await db.execute(stmt)
    await db.commit()
    user = result.fetchone()[0]

    logger.info("admin.local_user_created", new_user_email=body.email, by=str(admin.id))
    return user


@router.patch("/me/password", summary="Сменить пароль (только для локальных пользователей)")
async def change_my_password(
    body: PasswordChangeRequest,
    user: CurrentUser,
    db: DbDep,
) -> dict:
    if user.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password management is only available for local accounts",
        )

    from app.core.security import hash_password, verify_password
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    await db.execute(
        update(User).where(User.id == user.id).values(password_hash=hash_password(body.new_password))
    )
    await db.commit()
    logger.info("user.password_changed", user_id=str(user.id))
    return {"ok": True}


@router.patch("/admin/{user_id}/password", summary="Сбросить пароль (только admin, только локальные)")
async def reset_user_password(
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    admin: AdminDep,
    db: DbDep,
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset is only available for local accounts",
        )

    from app.core.security import hash_password
    await db.execute(
        update(User).where(User.id == user_id).values(password_hash=hash_password(body.new_password))
    )
    await db.commit()
    logger.info("admin.password_reset", target_user_id=str(user_id), by=str(admin.id))
    return {"ok": True}
