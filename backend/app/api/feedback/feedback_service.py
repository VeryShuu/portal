"""Business logic for feedback: create, status changes, replies, attachments."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from redis.asyncio import Redis
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uploads import safe_join_within, stream_upload_to_path
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.models.user import User
from app.schemas.feedback import (
    FeedbackAttachmentOut,
    FeedbackIn,
    FeedbackReplyIn,
    FeedbackReplyOut,
    FeedbackStatusIn,
)
from app.services.notifications import (
    notify_admins_new_feedback,
    notify_user_feedback_reply,
    notify_user_feedback_status_changed,
)

from . import feedback_repo
from ._common import (
    FEEDBACK_ATTACHMENT_ALLOWED_MIMES,
    FEEDBACK_ATTACHMENT_MAX_PER_TICKET,
    FEEDBACK_ATTACHMENT_MAX_SIZE,
    FEEDBACK_FILES_DIR,
    attachment_to_out,
    logger,
)


async def create_feedback(
    db: AsyncSession, redis: Redis, user: User, payload: FeedbackIn
) -> Feedback:
    fb = Feedback(
        user_id=user.id,
        category=payload.category.value,
        message=payload.message,
        page_url=payload.page_url,
        status="open",
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    try:
        await notify_admins_new_feedback(
            db,
            redis,
            feedback_id=fb.id,
            author_id=user.id,
            author_name=user.full_name,
            category=fb.category,
        )
    except Exception as exc:
        logger.exception("feedback.notify_admins_failed", error=str(exc))

    return fb


async def load_admin_feedback_or_404(db: AsyncSession, feedback_id: uuid.UUID) -> Feedback:
    fb = await feedback_repo.fetch_admin_feedback(db, feedback_id)
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return fb


async def update_status(
    db: AsyncSession,
    redis: Redis,
    feedback_id: uuid.UUID,
    payload: FeedbackStatusIn,
) -> Feedback:
    fb = await load_admin_feedback_or_404(db, feedback_id)
    old_status = fb.status
    new_status = payload.status.value

    fb.status = new_status
    fb.updated_at = func.now()
    await db.commit()
    await db.refresh(fb, attribute_names=["status", "updated_at"])

    if new_status == "closed" and old_status != "closed" and fb.user_id is not None:
        try:
            await notify_user_feedback_status_changed(
                db,
                redis,
                feedback_id=fb.id,
                user_id=fb.user_id,
                new_status=new_status,
            )
        except Exception as exc:
            logger.exception("feedback.notify_status_failed", error=str(exc))

    return fb


async def add_reply(
    db: AsyncSession,
    redis: Redis,
    admin: User,
    feedback_id: uuid.UUID,
    payload: FeedbackReplyIn,
) -> FeedbackReplyOut:
    fb = await feedback_repo.fetch_feedback_simple(db, feedback_id)
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    reply = FeedbackReply(
        feedback_id=fb.id,
        admin_id=admin.id,
        message=payload.message,
    )
    db.add(reply)

    fb.updated_at = func.now()
    if fb.status == "open":
        fb.status = "in_progress"

    await db.commit()
    await db.refresh(reply)

    if fb.user_id is not None and fb.user_id != admin.id:
        try:
            await notify_user_feedback_reply(
                db,
                redis,
                feedback_id=fb.id,
                user_id=fb.user_id,
                admin_name=admin.full_name,
            )
        except Exception as exc:
            logger.exception("feedback.notify_reply_failed", error=str(exc))

    return FeedbackReplyOut(
        id=reply.id,
        admin_id=reply.admin_id,
        admin_name=admin.full_name,
        message=reply.message,
        created_at=reply.created_at,
    )


async def load_feedback_for_attachment_access(
    db: AsyncSession, feedback_id: uuid.UUID, user: User
) -> Feedback:
    """Загружает обращение с проверкой прав на работу с вложениями.

    Доступ имеют автор обращения и администраторы.
    """
    fb = await feedback_repo.fetch_feedback_with_attachments(db, feedback_id)
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if user.role != "admin" and fb.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return fb


async def upload_attachment(
    db: AsyncSession,
    user: User,
    feedback_id: uuid.UUID,
    file: UploadFile,
) -> FeedbackAttachmentOut:
    fb = await load_feedback_for_attachment_access(db, feedback_id, user)

    if user.role != "admin" and fb.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot attach files to a closed ticket",
        )

    if len(fb.attachments or []) >= FEEDBACK_ATTACHMENT_MAX_PER_TICKET:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Attachment limit reached (max {FEEDBACK_ATTACHMENT_MAX_PER_TICKET})",
        )

    original_name = (file.filename or "file").strip() or "file"
    safe_stored = (
        f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', Path(original_name).name)[:200]}"
    )
    dest = FEEDBACK_FILES_DIR / str(feedback_id) / safe_stored

    size, mime = await stream_upload_to_path(
        file,
        dest,
        max_size=FEEDBACK_ATTACHMENT_MAX_SIZE,
        allowed_mimes=FEEDBACK_ATTACHMENT_ALLOWED_MIMES,
    )

    att = FeedbackAttachment(
        feedback_id=fb.id,
        filename=safe_stored,
        original_name=original_name,
        size_bytes=size,
        mime_type=mime or file.content_type,
        uploaded_by=user.id,
    )
    db.add(att)
    fb.updated_at = func.now()
    await db.commit()
    await db.refresh(att)
    return attachment_to_out(att)


async def resolve_attachment_for_download(
    db: AsyncSession,
    user: User,
    feedback_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> FeedbackAttachment:
    fb = await load_feedback_for_attachment_access(db, feedback_id, user)

    att = next((a for a in (fb.attachments or []) if a.id == attachment_id), None)
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", att.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return att


async def delete_attachment(
    db: AsyncSession,
    user: User,
    feedback_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> None:
    fb = await load_feedback_for_attachment_access(db, feedback_id, user)

    att = next((a for a in (fb.attachments or []) if a.id == attachment_id), None)
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    is_owner_of_attachment = att.uploaded_by == user.id
    is_admin = user.role == "admin"
    if not is_admin and not is_owner_of_attachment:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if not is_admin and fb.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify attachments on a closed ticket",
        )

    disk_path = safe_join_within(FEEDBACK_FILES_DIR, str(feedback_id), att.filename)
    disk_path.unlink(missing_ok=True)
    await db.delete(att)
    fb.updated_at = func.now()
    await db.commit()
