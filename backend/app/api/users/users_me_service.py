"""Users business-logic layer: эндпоинты текущего пользователя (/users/me)."""

from __future__ import annotations

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
    PasswordChangeRequest,
    PatchPreferencesRequest,
    PatchProfileRequest,
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


async def patch_my_profile(db: AsyncSession, user: User, body: PatchProfileRequest) -> User:
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


async def patch_my_preferences(db: AsyncSession, user: User, body: PatchPreferencesRequest) -> User:
    prefs = dict(user.preferences or {})

    if body.hidden_link_ids is not None:
        prefs["hidden_link_ids"] = body.hidden_link_ids
    if body.onboarding_completed is not None:
        prefs["onboarding_completed"] = body.onboarding_completed
    if body.onboarding_seen_step_ids is not None:
        seen = list(dict.fromkeys(str(x) for x in body.onboarding_seen_step_ids))
        # Hard cap to prevent unbounded growth (DoS via giant preferences JSON).
        if len(seen) > 500:
            seen = seen[-500:]
        prefs["onboarding_seen_step_ids"] = seen

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
