"""Helpdesk inline-media endpoints (картинки rich-редактора в ответах).

По образцу ``app/api/kb/media.py``: upload (streaming) + serve через nginx
``X-Accel-Redirect``. Картинки хранятся локально в папке тикета (как вложения),
в отдельной подпапке ``inline/`` — ``HELPDESK_FILES_DIR / "TKT-{number}" / "inline"``.

ACL: автор тикета ИЛИ агент/админ. Картинки приватны (как вложения) — доступ
только участникам переписки, иначе перебором относительного URL можно читать
чужие скриншоты.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.core.constants import (
    HELPDESK_FILES_DIR,
    HELPDESK_INLINE_IMAGE_MIMES,
    HELPDESK_MAX_ATTACHMENT_MB,
)
from app.core.uploads import stream_upload_to_path
from app.models.helpdesk import HelpdeskAgent, HelpdeskTicket
from app.schemas.kb_extra import MediaUploadResponse

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])


async def _is_helpdesk_agent(db: DbDep, *, user: CurrentUser) -> bool:
    """Мягкая проверка агентства (без 403, как ``require_helpdesk_agent``).

    Admin — суперсет (как везде в helpdesk). Нужна, потому что media-endpoint
    доступен и автору тикета, и агенту — ``HelpdeskAgentDep`` (бросающий 403)
    здесь не годится: он бы отсёк не-агента-автора ещё до проверки авторства.
    """
    if user.role == "admin":
        return True
    res = await db.execute(select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user.id))
    return res.first() is not None


def _ticket_inline_dir(ticket_number: int) -> Path:
    """Папка inline-картинок тикета: ``/data/helpdesk/TKT-{number}/inline``."""
    return HELPDESK_FILES_DIR / f"TKT-{ticket_number}" / "inline"


async def _fetch_ticket_for_media(
    db: DbDep, *, ticket_id: uuid.UUID, user: CurrentUser, is_agent: bool
) -> HelpdeskTicket:
    """Загрузить тикет с ACL-проверкой для media-endpoint.

    Автор тикета (``requester_user_id == user.id``) ИЛИ агент/админ. Иначе 404
    (не раскрываем существование тикета, как в ``fetch_ticket_for_user``).
    Нужен только ``number`` (для пути на диске) и ``id`` — без eager-load
    сообщений (media не работает с перепиской).
    """
    stmt = select(HelpdeskTicket).where(HelpdeskTicket.id == ticket_id)
    if not is_agent:
        # Заявитель видит только свои тикеты.
        stmt = stmt.where(HelpdeskTicket.requester_user_id == user.id)
    res = await db.execute(stmt)
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.post(
    "/tickets/{ticket_id}/inline-media",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить inline-картинку для rich-редактора ответа",
)
async def upload_ticket_inline_media(
    ticket_id: uuid.UUID,
    file: UploadFile,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> MediaUploadResponse:
    # Доступ: автор тикета ИЛИ helpdesk-агент/админ. Агентство проверяем мягко
    # (без 403) — ``_is_helpdesk_agent``, т.к. не-агент-автор тоже имеет право.
    is_agent = await _is_helpdesk_agent(db, user=user)
    ticket = await _fetch_ticket_for_media(db, ticket_id=ticket_id, user=user, is_agent=is_agent)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image extension. Allowed: .jpg, .jpeg, .png, .gif, .webp",
        )

    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "image").name, flags=re.ASCII)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = _ticket_inline_dir(ticket.number) / unique_name

    await stream_upload_to_path(
        file,
        dest,
        max_size=HELPDESK_MAX_ATTACHMENT_MB * 1024 * 1024,
        allowed_mimes=HELPDESK_INLINE_IMAGE_MIMES,
    )

    url = f"/api/v1/helpdesk/tickets/{ticket_id}/inline-media/{unique_name}"
    return MediaUploadResponse(url=url, filename=unique_name)


@router.get(
    "/tickets/{ticket_id}/inline-media/{filename}",
    summary="Раздать inline-картинку (через nginx X-Accel-Redirect)",
)
async def serve_ticket_inline_media(
    ticket_id: uuid.UUID,
    filename: str,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> Response:
    is_agent = await _is_helpdesk_agent(db, user=user)
    ticket = await _fetch_ticket_for_media(db, ticket_id=ticket_id, user=user, is_agent=is_agent)

    # Path-traversal guard (как в kb/media.py): только безопасные символы,
    # без каталогов.
    if not re.fullmatch(r"\w[\w.\-]{0,254}", filename) or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    ext = Path(filename).suffix.lower()
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

    # X-Accel-Redirect указывает на nginx location ``/internal/helpdesk-media/``
    # (alias → ``/data/helpdesk/``). Внутренний путь:
    # ``TKT-{number}/inline/{filename}`` (совпадает с FS-структурой).
    internal_path = (
        f"/internal/helpdesk-media/TKT-{ticket.number}/inline/{quote(filename)}"
    )
    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            "X-Accel-Redirect": internal_path,
            "Content-Type": mime_type,
            "X-Content-Type-Options": "nosniff",
        },
    )
