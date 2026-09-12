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
from app.models.user import User
from app.schemas.user import (
    PasswordChangeRequest,
    PatchPreferencesRequest,
    PatchProfileRequest,
)
from app.services.audit import push_audit_event
from app.services.session import invalidate_all_user_sessions

from . import avatar_service, users_repo
from ._common import logger


async def patch_my_profile(db: AsyncSession, user: User, body: PatchProfileRequest) -> User:
    updates: dict = {}

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

    if body.avatar_focal_x is not None:
        updates["avatar_focal_x"] = body.avatar_focal_x
    if body.avatar_focal_y is not None:
        updates["avatar_focal_y"] = body.avatar_focal_y
    if body.avatar_focal_zoom is not None:
        updates["avatar_focal_zoom"] = body.avatar_focal_zoom

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
        # Вид завершения пишем только при повторной отправке флага completed,
        # чтобы старый маркер не затирался PATCH'ами без него.
        if body.onboarding_completed_via is not None:
            prefs["onboarding_completed_via"] = body.onboarding_completed_via
    if body.onboarding_seen_step_ids is not None:
        seen = list(dict.fromkeys(str(x) for x in body.onboarding_seen_step_ids))
        # Hard cap to prevent unbounded growth (DoS via giant preferences JSON).
        if len(seen) > 500:
            seen = seen[-500:]
        prefs["onboarding_seen_step_ids"] = seen
    if body.chat_notifications_enabled is not None:
        prefs["chat_notifications_enabled"] = body.chat_notifications_enabled

    await users_repo.update_user_fields(db, user.id, {"preferences": prefs})
    await db.commit()
    await db.refresh(user)
    return user


async def upload_avatar(db: AsyncSession, user: User, file: UploadFile) -> User:
    return await avatar_service.save_avatar(db, user, file)


async def delete_avatar(db: AsyncSession, user: User) -> User:
    return await avatar_service.remove_avatar(db, user)


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
