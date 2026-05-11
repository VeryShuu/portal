"""API обратной связи (Feedback)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.api.kb._common import _rfc5987_filename
from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_path
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.schemas.feedback import (
    FeedbackAdminListOut,
    FeedbackAdminOut,
    FeedbackAttachmentOut,
    FeedbackIn,
    FeedbackListOut,
    FeedbackOut,
    FeedbackReplyIn,
    FeedbackReplyOut,
    FeedbackStatusIn,
)
from app.services.notifications import (
    notify_admins_new_feedback,
    notify_user_feedback_reply,
    notify_user_feedback_status_changed,
)

FEEDBACK_FILES_DIR = Path("/data/feedback/files")
FEEDBACK_ATTACHMENT_MAX_SIZE = 10 * 1024 * 1024
FEEDBACK_ATTACHMENT_MAX_PER_TICKET = 5
FEEDBACK_ATTACHMENT_ALLOWED_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
    "text/plain",
    "application/zip",
    "application/x-zip-compressed",
}

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = get_logger(__name__)


def _reply_to_out(reply: FeedbackReply) -> FeedbackReplyOut:
    admin_name = reply.admin.full_name if reply.admin else None
    return FeedbackReplyOut(
        id=reply.id,
        admin_id=reply.admin_id,
        admin_name=admin_name,
        message=reply.message,
        created_at=reply.created_at,
    )


def _attachment_to_out(att: FeedbackAttachment) -> FeedbackAttachmentOut:
    return FeedbackAttachmentOut(
        id=att.id,
        original_name=att.original_name,
        size_bytes=att.size_bytes,
        mime_type=att.mime_type,
        created_at=att.created_at,
        download_url=f"/api/v1/feedback/{att.feedback_id}/attachments/{att.id}",
    )


def _feedback_to_out(fb: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=fb.id,
        category=fb.category,
        message=fb.message,
        page_url=fb.page_url,
        status=fb.status,
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        replies=[_reply_to_out(r) for r in (fb.replies or [])],
        attachments=[_attachment_to_out(a) for a in (fb.attachments or [])],
    )


def _feedback_to_admin_out(fb: Feedback) -> FeedbackAdminOut:
    author_name = fb.author.full_name if fb.author else None
    author_email = fb.author.email if fb.author else None
    return FeedbackAdminOut(
        id=fb.id,
        category=fb.category,
        message=fb.message,
        page_url=fb.page_url,
        status=fb.status,
        created_at=fb.created_at,
        updated_at=fb.updated_at,
        replies=[_reply_to_out(r) for r in (fb.replies or [])],
        attachments=[_attachment_to_out(a) for a in (fb.attachments or [])],
        user_id=fb.user_id,
        author_name=author_name,
        author_email=author_email,
    )


@router.post(
    "",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать обращение",
    dependencies=[Depends(RateLimiter(times=5, minutes=1))],
)
async def create_feedback(
    payload: FeedbackIn,
    user: CurrentUser,
    db: DbDep,
    redis: RedisDep,
) -> FeedbackOut:
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

    return _feedback_to_out(fb)


@router.get(
    "/my",
    response_model=FeedbackListOut,
    summary="Мои обращения",
)
async def list_my_feedback(
    user: CurrentUser,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FeedbackListOut:
    if status_filter and status_filter not in ("open", "in_progress", "closed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )

    conditions = [Feedback.user_id == user.id]
    if status_filter:
        conditions.append(Feedback.status == status_filter)

    total_res = await db.execute(select(func.count()).select_from(Feedback).where(*conditions))
    total = int(total_res.scalar_one())

    res = await db.execute(
        select(Feedback)
        .where(*conditions)
        .options(
            selectinload(Feedback.replies).joinedload(FeedbackReply.admin),
            selectinload(Feedback.attachments),
        )
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = res.scalars().unique().all()
    return FeedbackListOut(items=[_feedback_to_out(i) for i in items], total=total)


@router.get(
    "/my/{feedback_id}",
    response_model=FeedbackOut,
    summary="Моё обращение",
)
async def get_my_feedback(
    feedback_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> FeedbackOut:
    res = await db.execute(
        select(Feedback)
        .where(Feedback.id == feedback_id, Feedback.user_id == user.id)
        .options(
            selectinload(Feedback.replies).joinedload(FeedbackReply.admin),
            selectinload(Feedback.attachments),
        )
    )
    fb = res.unique().scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _feedback_to_out(fb)


@router.get(
    "",
    response_model=FeedbackAdminListOut,
    summary="Все обращения (админ)",
)
async def list_all_feedback(
    _admin: AdminDep,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FeedbackAdminListOut:
    if status_filter and status_filter not in ("open", "in_progress", "closed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid status"
        )
    if category and category not in ("bug", "suggestion", "other"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid category"
        )

    conditions = []
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    if category:
        conditions.append(Feedback.category == category)
    if q:
        conditions.append(Feedback.message.ilike(f"%{q}%"))

    total_q = select(func.count()).select_from(Feedback)
    if conditions:
        total_q = total_q.where(*conditions)
    total_res = await db.execute(total_q)
    total = int(total_res.scalar_one())

    list_q = (
        select(Feedback)
        .options(
            selectinload(Feedback.replies).joinedload(FeedbackReply.admin),
            selectinload(Feedback.attachments),
        )
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        list_q = list_q.where(*conditions)

    res = await db.execute(list_q)
    items = res.scalars().unique().all()
    return FeedbackAdminListOut(
        items=[_feedback_to_admin_out(i) for i in items],
        total=total,
    )


async def _load_feedback_admin(db, feedback_id: uuid.UUID) -> Feedback:
    res = await db.execute(
        select(Feedback)
        .where(Feedback.id == feedback_id)
        .options(
            selectinload(Feedback.replies).joinedload(FeedbackReply.admin),
            selectinload(Feedback.attachments),
        )
    )
    fb = res.unique().scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return fb


@router.get(
    "/{feedback_id}",
    response_model=FeedbackAdminOut,
    summary="Обращение (админ)",
)
async def get_feedback_admin(
    feedback_id: uuid.UUID,
    _admin: AdminDep,
    db: DbDep,
) -> FeedbackAdminOut:
    fb = await _load_feedback_admin(db, feedback_id)
    return _feedback_to_admin_out(fb)


@router.patch(
    "/{feedback_id}/status",
    response_model=FeedbackAdminOut,
    summary="Изменить статус обращения",
)
async def update_feedback_status(
    feedback_id: uuid.UUID,
    payload: FeedbackStatusIn,
    _admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> FeedbackAdminOut:
    fb = await _load_feedback_admin(db, feedback_id)
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

    return _feedback_to_admin_out(fb)


@router.post(
    "/{feedback_id}/reply",
    response_model=FeedbackReplyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ответить на обращение",
    dependencies=[Depends(RateLimiter(times=30, minutes=1))],
)
async def reply_to_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackReplyIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> FeedbackReplyOut:
    res = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    fb = res.scalar_one_or_none()
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


async def _load_feedback_for_attachment_access(
    db, feedback_id: uuid.UUID, user
) -> Feedback:
    """Загружает обращение с проверкой прав на работу с вложениями.

    Доступ имеют автор обращения и администраторы.
    """
    res = await db.execute(
        select(Feedback)
        .where(Feedback.id == feedback_id)
        .options(selectinload(Feedback.attachments))
    )
    fb = res.unique().scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if user.role != "admin" and fb.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return fb


@router.post(
    "/{feedback_id}/attachments",
    response_model=FeedbackAttachmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Прикрепить файл к обращению",
    dependencies=[Depends(RateLimiter(times=20, minutes=1))],
)
async def upload_feedback_attachment(
    feedback_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser,
    db: DbDep,
) -> FeedbackAttachmentOut:
    fb = await _load_feedback_for_attachment_access(db, feedback_id, user)

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
    safe_stored = f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', Path(original_name).name)[:200]}"
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
    return _attachment_to_out(att)


@router.get(
    "/{feedback_id}/attachments/{attachment_id}",
    summary="Скачать вложение обращения",
)
async def download_feedback_attachment(
    feedback_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    fb = await _load_feedback_for_attachment_access(db, feedback_id, user)

    att = next((a for a in (fb.attachments or []) if a.id == attachment_id), None)
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", att.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    internal_path = f"/internal/feedback-files/{feedback_id}/{att.filename}"
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": att.mime_type or "application/octet-stream",
            "Content-Disposition": _rfc5987_filename(att.original_name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{feedback_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить вложение обращения",
)
async def delete_feedback_attachment(
    feedback_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> Response:
    fb = await _load_feedback_for_attachment_access(db, feedback_id, user)

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

    disk_path = FEEDBACK_FILES_DIR / str(feedback_id) / att.filename
    disk_path.unlink(missing_ok=True)
    await db.delete(att)
    fb.updated_at = func.now()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
