"""Users business-logic layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, UploadFile, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    SESSION_COOKIE_NAME,
    hash_password_async,
    verify_password_async,
)
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
)
from app.services.audit import push_audit_event
from app.services.session import invalidate_all_user_sessions

from . import users_repo
from ._common import (
    ALLOWED_IMG_TYPES,
    AVATARS_DIR,
    CONTENT_TYPE_TO_EXT,
    MAX_AVATAR_SIZE,
    logger,
)


async def patch_my_profile(
    db: AsyncSession, user: User, body: PatchProfileRequest
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

    await users_repo.update_user_fields(db, user.id, updates)
    await db.commit()
    await db.refresh(user)
    return user


async def patch_my_preferences(
    db: AsyncSession, user: User, body: PatchPreferencesRequest
) -> User:
    prefs = dict(user.preferences or {})

    if body.hidden_link_ids is not None:
        prefs["hidden_link_ids"] = body.hidden_link_ids
    if body.onboarding_completed is not None:
        prefs["onboarding_completed"] = body.onboarding_completed

    await users_repo.update_user_fields(db, user.id, {"preferences": prefs})
    await db.commit()
    await db.refresh(user)
    return user


async def upload_avatar(db: AsyncSession, user: User, file: UploadFile) -> User:
    if file.content_type not in ALLOWED_IMG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image type",
        )

    ext = CONTENT_TYPE_TO_EXT.get(file.content_type or "", "jpg")
    filename = f"{user.id}.{ext}"
    file_path = AVATARS_DIR / filename

    await stream_upload_to_path(
        file,
        file_path,
        max_size=MAX_AVATAR_SIZE,
        allowed_mimes=ALLOWED_IMG_TYPES,
    )

    avatar_url = f"/media/avatars/{filename}"
    await users_repo.update_user_fields(db, user.id, {"avatar_url": avatar_url})
    await db.commit()
    await db.refresh(user)
    return user


async def enqueue_keycloak_sync(
    request: Request, admin: User, redis: Redis
) -> dict:
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Job queue is not available"
        )
    job = await arq_pool.enqueue_job("sync_users_from_keycloak")
    await push_audit_event(
        redis,
        event_type="user.sync_requested",
        user_id=str(admin.id),
        resource_type="user",
        metadata={"job_id": job.job_id if job else None},
    )
    return {"job_id": job.job_id if job else None, "status": "queued"}


async def change_user_role(
    db: AsyncSession,
    redis: Redis,
    admin: User,
    user_id: uuid.UUID,
    body: PatchRoleRequest,
) -> User:
    if body.role not in ("reader", "editor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid role"
        )

    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    user = await users_repo.fetch_user_any(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    old_role = user.role
    await users_repo.update_user_fields(db, user_id, {"role": body.role})
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


async def create_local_user(
    db: AsyncSession,
    redis: Redis,
    admin: User,
    body: LocalUserCreateRequest,
) -> User:
    from app.api import users as _users_pkg

    if not _users_pkg.settings.local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local authentication is disabled",
        )

    existing = await users_repo.find_active_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    password_hash = await hash_password_async(body.password)
    user = await users_repo.insert_local_user(
        db,
        email=body.email,
        full_name=body.full_name,
        password_hash=password_hash,
        role=body.role,
    )
    await db.commit()
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


async def get_user_groups(db: AsyncSession, user_id: uuid.UUID) -> dict:
    target = await users_repo.fetch_active_user(db, user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return {"groups": list(target.keycloak_groups or [])}


async def admin_patch_profile(
    db: AsyncSession,
    redis: Redis,
    admin: User,
    user_id: uuid.UUID,
    body: AdminPatchProfileRequest,
) -> User:
    target = await users_repo.fetch_active_user(db, user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
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
    await users_repo.update_user_fields(db, user_id, updates)
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


async def delete_user(
    db: AsyncSession, redis: Redis, admin: User, user_id: uuid.UUID
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    target = await users_repo.fetch_active_user(db, user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    news_versions_affected = await users_repo.count_news_versions_for_editor(
        db, user_id
    )

    await users_repo.soft_delete_user(db, user_id)
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
            "news_versions_editor_id_affected": news_versions_affected,
        },
    )
    logger.info(
        "admin.user_deleted",
        target_user_id=str(user_id),
        email=target.email,
        by=str(admin.id),
    )


async def change_my_password(
    db: AsyncSession,
    redis: Redis,
    request: Request,
    user: User,
    body: PasswordChangeRequest,
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
    await users_repo.update_user_fields(db, user.id, {"password_hash": new_hash})
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


async def reset_user_password(
    db: AsyncSession,
    redis: Redis,
    admin: User,
    user_id: uuid.UUID,
    body: PasswordResetRequest,
) -> dict:
    target = await users_repo.fetch_user_any(db, user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if target.auth_source != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset is only available for local accounts",
        )

    new_hash = await hash_password_async(body.new_password)
    await users_repo.update_user_fields(db, user_id, {"password_hash": new_hash})
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
