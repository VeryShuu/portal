"""Users API: справочник сотрудников, профиль, синхронизация."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.core.config import get_settings
from app.core.constants import ALLOWED_AVATAR_IMG_TYPES
from app.core.logging import get_logger
from app.core.security import SESSION_COOKIE_NAME, hash_password_async, verify_password_async
from app.core.uploads import stream_upload_to_path
from app.models.user import User
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
from app.services.audit import push_audit_event
from app.services.session import invalidate_all_user_sessions

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()
logger = get_logger(__name__)

AVATARS_DIR = Path(os.getenv("DATA_DIR", "/data")) / "avatars"
ALLOWED_IMG_TYPES = ALLOWED_AVATAR_IMG_TYPES
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@router.get("", response_model=UserList, summary="Список сотрудников")
async def list_users(
    db: DbDep,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> UserList:
    conditions = [User.deleted_at.is_(None)]
    if q:
        pattern = f"%{q}%"
        conditions.append(User.full_name.ilike(pattern) | User.email.ilike(pattern))
    if department:
        conditions.append(User.department == department)

    total_result = await db.execute(select(func.count(User.id)).where(*conditions))
    total = total_result.scalar_one()

    stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
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
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
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
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid presence_status",
            )
        updates["presence_status"] = body.presence_status

    if body.lang is not None:
        if body.lang not in ("ru", "en"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid lang",
            )
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
    if body.onboarding_completed is not None:
        prefs["onboarding_completed"] = body.onboarding_completed

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image type",
        )

    ext = _CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    filename = f"{user.id}.{ext}"
    file_path = AVATARS_DIR / filename

    # P0-4/P0-5: streaming + real MIME validation.
    await stream_upload_to_path(
        file,
        file_path,
        max_size=MAX_AVATAR_SIZE,
        allowed_mimes=ALLOWED_IMG_TYPES,
    )

    avatar_url = f"/media/avatars/{filename}"
    await db.execute(update(User).where(User.id == user.id).values(avatar_url=avatar_url))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/admin/sync", summary="Синхронизировать пользователей из Keycloak")
async def sync_users_from_keycloak(
    admin: AdminDep,
    redis: RedisDep,
) -> dict:
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    # P0-8: function lives in app.worker.tasks.news (registered there in worker/main.py).
    job = await pool.enqueue_job("sync_users_from_keycloak")
    await pool.aclose()
    await push_audit_event(
        redis,
        event_type="user.sync_requested",
        user_id=str(admin.id),
        resource_type="user",
        metadata={"job_id": job.job_id if job else None},
    )
    return {"job_id": job.job_id if job else None, "status": "queued"}


@router.patch("/admin/{user_id}/role", summary="Сменить роль пользователя")
async def change_user_role(
    user_id: uuid.UUID,
    body: PatchRoleRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> UserPublic:
    if body.role not in ("reader", "editor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid role"
        )

    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_role = user.role
    await db.execute(update(User).where(User.id == user_id).values(role=body.role))
    await db.commit()
    await db.refresh(user)
    await push_audit_event(
        redis,
        event_type="user.role_changed",
        user_id=str(admin.id),
        resource_type="user",
        resource_id=str(user_id),
        metadata={"old_role": old_role, "new_role": body.role},
    )

    logger.info(
        "admin.role_changed",
        target_user_id=str(user_id),
        new_role=body.role,
        by=str(admin.id),
    )
    return user


@router.post("/admin/local", response_model=UserPublic, summary="Создать локального пользователя")
async def create_local_user(
    body: LocalUserCreateRequest,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> User:
    if not settings.local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local authentication is disabled",
        )

    existing = await db.execute(
        select(User).where(
            func.lower(User.email) == body.email.lower(),
            User.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    now = datetime.now(UTC)
    stmt = (
        pg_insert(User)
        .values(
            email=body.email,
            full_name=body.full_name,
            auth_source="local",
            password_hash=await hash_password_async(body.password),
            role=body.role,
            updated_at=now,
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    await db.commit()
    user = result.scalars().one()
    await push_audit_event(
        redis,
        event_type="user.created",
        user_id=str(admin.id),
        resource_type="user",
        resource_id=str(user.id),
        metadata={"auth_source": "local", "role": body.role},
    )

    logger.info("admin.local_user_created", new_user_email=body.email, by=str(admin.id))
    return user


@router.get(
    "/admin/{user_id}/groups",
    summary="Группы Keycloak пользователя (только для админа)",
)
async def admin_get_user_groups(
    user_id: uuid.UUID,
    admin: AdminDep,
    db: DbDep,
) -> dict:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"groups": list(target.keycloak_groups or [])}


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
) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Profile editing is only available for local accounts",
        )

    updates: dict = {}
    if body.full_name is not None:
        updates["full_name"] = body.full_name
    if body.department is not None:
        updates["department"] = body.department
    if body.position is not None:
        updates["position"] = body.position
    if body.phone is not None:
        updates["phone"] = body.phone

    if not updates:
        return target

    updates["updated_at"] = datetime.now(UTC)
    await db.execute(update(User).where(User.id == user_id).values(**updates))
    await db.commit()
    await db.refresh(target)
    await push_audit_event(
        redis,
        event_type="user.profile_updated",
        user_id=str(admin.id),
        resource_type="user",
        resource_id=str(user_id),
        metadata={"fields": list(updates.keys())},
    )
    return target


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
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    news_versions_affected = await db.scalar(
        text("SELECT COUNT(*) FROM news_versions WHERE editor_id = :uid"),
        {"uid": user_id},
    ) or 0

    now = datetime.now(UTC)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(deleted_at=now, updated_at=now)
    )
    await db.commit()
    await invalidate_all_user_sessions(redis, str(user_id))
    await push_audit_event(
        redis,
        event_type="user.deleted",
        user_id=str(admin.id),
        resource_type="user",
        resource_id=str(user_id),
        metadata={
            "email": target.email,
            "auth_source": target.auth_source,
            "soft_delete": True,
            "news_versions_editor_id_affected": int(news_versions_affected),
        },
    )
    logger.info(
        "admin.user_deleted",
        target_user_id=str(user_id),
        email=target.email,
        by=str(admin.id),
    )


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
    if user.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password management is only available for local accounts",
        )

    if not user.password_hash or not await verify_password_async(
        body.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    new_hash = await hash_password_async(body.new_password)
    await db.execute(update(User).where(User.id == user.id).values(password_hash=new_hash))
    await db.commit()
    await invalidate_all_user_sessions(
        redis,
        str(user.id),
        except_session_id=request.cookies.get(SESSION_COOKIE_NAME),
    )
    await push_audit_event(
        redis,
        event_type="user.password_changed",
        user_id=str(user.id),
        user_email=user.email,
    )
    logger.info("user.password_changed", user_id=str(user.id))
    return {"ok": True}


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
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset is only available for local accounts",
        )

    new_hash = await hash_password_async(body.new_password)
    await db.execute(update(User).where(User.id == user_id).values(password_hash=new_hash))
    await db.commit()
    await invalidate_all_user_sessions(redis, str(user_id))
    await push_audit_event(
        redis,
        event_type="user.password_reset",
        user_id=str(admin.id),
        resource_type="user",
        resource_id=str(user_id),
    )
    logger.info("admin.password_reset", target_user_id=str(user_id), by=str(admin.id))
    return {"ok": True}
