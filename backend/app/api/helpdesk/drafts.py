"""Draft-attachment endpoints — inline images for the ticket **creation** form.

The reply-form inline-media endpoint (``/tickets/{id}/inline-media``) requires a
``ticket_id``, which does not exist yet while creating a ticket. These endpoints
bridge that gap: a draft image is uploaded here, referenced from
``description_html``, and backfilled into the ticket's permanent inline folder on
``POST /tickets`` (see ``services/helpdesk/drafts.py::backfill_draft_images``).

ACL: only the owner (``uploaded_by_user_id == current_user.id``) can create or
serve drafts. Drafts are private — a leaked draft URL is worthless to anyone
else (404). Orphan drafts are purged by ``cleanup_expired_drafts`` after the TTL.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi_limiter.depends import RateLimiter

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.schemas.kb_extra import MediaUploadResponse
from app.services.helpdesk.drafts import (
    create_draft_attachment,
    get_draft_for_user,
)

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])


@router.post(
    "/draft-attachments",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить inline-картинку для формы создания заявки (draft)",
    dependencies=[Depends(RateLimiter(times=20, minutes=1))],
)
async def upload_draft_attachment(
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    # Растровые форматы только (без SVG — XSS через <script> в SVG), как у
    # inline-media endpoint ответов. ``create_draft_attachment`` стримит файл на
    # диск с magic-MIME проверкой и лимитом HELPDESK_MAX_ATTACHMENT_MB.
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image extension. Allowed: .jpg, .jpeg, .png, .gif, .webp",
        )

    draft = await create_draft_attachment(db, user=user, file=file)
    # ``get_db()`` (``autocommit=False``) не коммитит автоматически — без
    # явного commit'а flush'нутая строка теряется при ``session.close()``
    # (подтверждено на проде: POST возвращал id, но GET → 404, строка не
    # сохранялась). Коммитим сразу — draft должен жить независимо, до
    # backfill'а при ``create_ticket`` (минуты/часы) или TTL-cleanup.
    await db.commit()
    url = f"/api/v1/helpdesk/draft-attachments/{draft.id}"
    return MediaUploadResponse(url=url, filename=draft.filename)


@router.get(
    "/draft-attachments/{draft_id}",
    summary="Раздать draft-картинку (через nginx X-Accel-Redirect; только владелец)",
)
async def serve_draft_attachment(
    draft_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    # 404 и для отсутствующих, и для чужих — не раскрываем существование draft'а.
    draft = await get_draft_for_user(db, draft_id=draft_id, user_id=user.id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    # Path-traversal guard (как в kb/media.py и helpdesk/media.py): только
    # безопасные символы, без каталогов.
    if (
        not re.fullmatch(r"\w[\w.\-]{0,254}", draft.filename)
        or "/" in draft.filename
        or "\\" in draft.filename
    ):  # noqa: E501
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    ext = Path(draft.filename).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".gif":
        mime_type = "image/gif"
    elif ext == ".webp":
        mime_type = "image/webp"
    else:
        mime_type = "application/octet-stream"

    # X-Accel-Redirect → nginx location ``/internal/helpdesk-media/drafts/``
    # (alias → ``/data/helpdesk/drafts/``). Внутренний путь:
    # ``usr-{user_id}/{filename}`` — совпадает с FS-структурой ``draft_dir``.
    internal_path = (
        f"/internal/helpdesk-media/drafts/usr-{draft.uploaded_by_user_id}/{quote(draft.filename)}"
    )
    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": mime_type,
            "X-Content-Type-Options": "nosniff",
        },
    )
