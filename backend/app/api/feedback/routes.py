"""HTTP layer for the feedback API package — thin endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter

from app.api.deps import AdminDep, CurrentUser, DbDep, RedisDep
from app.api.kb._common import _rfc5987_filename
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

from . import feedback_repo, feedback_service
from ._common import feedback_to_admin_out, feedback_to_out

router = APIRouter(prefix="/feedback", tags=["feedback"])


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
    fb = await feedback_service.create_feedback(db, redis, user, payload)
    return feedback_to_out(fb)


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
    total = await feedback_repo.count_my_feedback(
        db, user_id=user.id, status_filter=status_filter
    )
    items = await feedback_repo.list_my_feedback(
        db,
        user_id=user.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return FeedbackListOut(items=[feedback_to_out(i) for i in items], total=total)


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
    fb = await feedback_repo.fetch_my_feedback(
        db, feedback_id=feedback_id, user_id=user.id
    )
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return feedback_to_out(fb)


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

    total = await feedback_repo.count_admin_feedback(
        db, status_filter=status_filter, category=category, q=q
    )
    items = await feedback_repo.list_admin_feedback(
        db,
        status_filter=status_filter,
        category=category,
        q=q,
        limit=limit,
        offset=offset,
    )
    return FeedbackAdminListOut(
        items=[feedback_to_admin_out(i) for i in items],
        total=total,
    )


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
    fb = await feedback_service.load_admin_feedback_or_404(db, feedback_id)
    return feedback_to_admin_out(fb)


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
    fb = await feedback_service.update_status(db, redis, feedback_id, payload)
    return feedback_to_admin_out(fb)


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
    return await feedback_service.add_reply(db, redis, admin, feedback_id, payload)


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
    return await feedback_service.upload_attachment(db, user, feedback_id, file)


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
    att = await feedback_service.resolve_attachment_for_download(
        db, user, feedback_id, attachment_id
    )
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
    await feedback_service.delete_attachment(db, user, feedback_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
