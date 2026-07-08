"""Helpdesk attachment storage — local filesystem (Этап 4).

Хранение локальное, по образцу feedback (``/data/feedback/files/``): файлы
лежат в ``/data/helpdesk/TKT-{number}/{filename}``, где ``filename`` —
безопасное имя на диске (``{uuid}_{sanitized}``), а оригинальное имя
сохраняется в ``original_name`` для ``Content-Disposition``. Nextcloud **не**
используется (см. ТЗ §1.3.2).

Upload — streaming через ``stream_upload_to_path`` (MIME через ``python-magic``
по первым байтам, лимит размера, path-traversal guard). Download — вызывающий
роутер читает ``disk_path`` и отдаёт ``StreamingResponse`` через ``aiofiles``.
Файлы удаляются с диска по CASCADE (вместе с тикетом/сообщением) через
``delete_attachment_files``.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    HELPDESK_ATTACHMENT_ALLOWED_MIMES,
    HELPDESK_FILES_DIR,
    HELPDESK_MAX_ATTACHMENT_MB,
    HELPDESK_MAX_TOTAL_INGRESS_MB,
)
from app.core.logging import get_logger
from app.core.uploads import magic, stream_upload_to_path
from app.models.helpdesk import HelpdeskAgent, HelpdeskAttachment, HelpdeskTicket
from app.models.user import User

logger = get_logger(__name__)

# Path-traversal guard: только безопасные символы в имени файла на диссе.
# Совпадает с проверкой feedback (ТЗ §3.3).
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,254}$")

_MAX_ATTACHMENT_BYTES = HELPDESK_MAX_ATTACHMENT_MB * 1024 * 1024
_MAX_TOTAL_BYTES = HELPDESK_MAX_TOTAL_INGRESS_MB * 1024 * 1024

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def ticket_dir(ticket_number: int) -> Path:
    """Папка тикета на диске: ``/data/helpdesk/TKT-{number}``."""
    return HELPDESK_FILES_DIR / f"TKT-{ticket_number}"


def disk_path(attachment: HelpdeskAttachment, ticket_number: int) -> Path:
    """Полный путь файла вложения на диске + path-traversal guard."""
    if not _SAFE_FILENAME_RE.match(attachment.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return ticket_dir(ticket_number) / attachment.filename


def _safe_stored_name(original: str) -> str:
    """Имя на диске: ``{uuid}_{sanitized_base}``. Sanitize — оставляем только
    ``[A-Za-z0-9._-]`` и обрезаем базовое имя (без каталогов)."""
    base = Path(original).name[:200]
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", base) or "file"
    return f"{uuid.uuid4().hex}_{sanitized}"


async def upload_attachments(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message_id: uuid.UUID,
    files: list[UploadFile],
    actor: User,
) -> list[HelpdeskAttachment]:
    """Streaming-save списка файлов в папку тикета и создание записей в БД.

    Проверяет: MIME (через magic), лимит одного файла (``HELPDESK_MAX_ATTACHMENT_MB``)
    и суммарный лимит (``HELPDESK_MAX_TOTAL_INGRESS_MB``). Все файлы одного
    запроса пишутся в рамках одной транзакции с бизнес-операцией (создание
    тикета/сообщения) — caller делает ``commit``.
    """
    if not files:
        return []

    total_so_far = 0
    created: list[HelpdeskAttachment] = []
    dest_dir = ticket_dir(ticket.number)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        original_name = (file.filename or "file").strip() or "file"
        stored_name = _safe_stored_name(original_name)
        dest = dest_dir / stored_name
        size, mime = await stream_upload_to_path(
            file,
            dest,
            max_size=_MAX_ATTACHMENT_BYTES,
            allowed_mimes=HELPDESK_ATTACHMENT_ALLOWED_MIMES,
        )
        total_so_far += size
        if total_so_far > _MAX_TOTAL_BYTES:
            # Превышен суммарный лимит — откатываем этот файл.
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Total attachments size exceeds {_MAX_TOTAL_BYTES} bytes",
            )
        att = _build_attachment(
            db,
            ticket=ticket,
            message_id=message_id,
            stored_name=stored_name,
            original_name=original_name,
            content_type=mime or file.content_type or "application/octet-stream",
            size=size,
            uploaded_by_user_id=actor.id,
        )
        created.append(att)

    return created


async def save_image_bytes(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message_id: uuid.UUID,
    data: bytes,
    original_name: str,
    total_tracker: _TotalTracker | None = None,
) -> HelpdeskAttachment | None:
    """Сохранить байты (inline ``cid:`` или выкачанная внешняя картинка) в FS и
    создать запись ``HelpdeskAttachment``.

    Источник — ``bytes``, а не ``UploadFile`` (для email-ingress: inline-части и
    httpx-выкачка). Переиспользует те же проверки, что и ``upload_attachments``:
    MIME через ``magic.from_buffer`` по первым байтам, лимит одного файла и
    (опционально) суммарный лимит через ``total_tracker``.

    Возвращает ``None`` (и ничего не пишет на диск), если данные пусты, не прошли
    MIME-валидацию или превышен лимит — это best-effort путь ingress, одна
    невалидная картинка не должна валить весь тикет. Caller делает ``commit``.
    """
    if not data:
        return None

    detected = _detect_mime(data)
    effective = detected or "application/octet-stream"
    if effective not in HELPDESK_ATTACHMENT_ALLOWED_MIMES:
        logger.warning(
            "helpdesk.attachment.inline.rejected_mime",
            original_name=original_name,
            detected_mime=detected,
        )
        return None

    if len(data) > _MAX_ATTACHMENT_BYTES:
        logger.warning(
            "helpdesk.attachment.inline.too_large",
            original_name=original_name,
            size=len(data),
            max=_MAX_ATTACHMENT_BYTES,
        )
        return None

    if total_tracker is not None and total_tracker.total + len(data) > _MAX_TOTAL_BYTES:
        logger.warning(
            "helpdesk.attachment.inline.total_exceeded",
            original_name=original_name,
        )
        return None

    dest_dir = ticket_dir(ticket.number)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_name = _safe_stored_name(original_name)
    dest = dest_dir / stored_name

    async with aiofiles.open(dest, "wb") as out:
        await out.write(data)

    if total_tracker is not None:
        total_tracker.total += len(data)

    att = _build_attachment(
        db,
        ticket=ticket,
        message_id=message_id,
        stored_name=stored_name,
        original_name=original_name,
        content_type=effective,
        size=len(data),
        uploaded_by_user_id=None,
    )
    # id генерится в БД (``gen_random_uuid()`` server-side) — flush, чтобы caller
    # сразу получил ``att.id`` (нужно для переписывания img-src на
    # ``/api/v1/helpdesk/attachments/{id}`` при локализации картинок ingress).
    await db.flush()
    return att


class _TotalTracker:
    """Счётчик суммарного размера вложений одного письма (для лимита
    ``HELPDESK_MAX_TOTAL_INGRESS_MB`` при последовательном сохранении inline +
    external картинок + attach-частей)."""

    def __init__(self) -> None:
        self.total: int = 0


def _detect_mime(data: bytes) -> str | None:
    """MIME через ``python-magic`` по первым байтам (как ``stream_upload_to_path``)."""
    try:
        if magic is not None and data:
            return magic.from_buffer(data[:2048], mime=True)
    except Exception:
        return None
    return None


def _build_attachment(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message_id: uuid.UUID,
    stored_name: str,
    original_name: str,
    content_type: str,
    size: int,
    uploaded_by_user_id: uuid.UUID | None,
) -> HelpdeskAttachment:
    """Создать запись ``HelpdeskAttachment`` и добавить в сессию."""
    att = HelpdeskAttachment(
        ticket_id=ticket.id,
        message_id=message_id,
        filename=stored_name,
        original_name=original_name,
        content_type=content_type,
        size_bytes=size,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.add(att)
    return att


async def fetch_for_download(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    user: User,
) -> tuple[HelpdeskAttachment, HelpdeskTicket]:
    """Загрузить вложение с ACL-проверкой: автор тикета ИЛИ helpdesk-агент/
    админ. Чужое вложение → 404 (не раскрываем существование)."""
    res = await db.execute(
        select(HelpdeskAttachment)
        .where(HelpdeskAttachment.id == attachment_id)
        .options(selectinload(HelpdeskAttachment.message))
    )
    att = res.scalars().unique().one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    ticket_res = await db.execute(select(HelpdeskTicket).where(HelpdeskTicket.id == att.ticket_id))
    ticket = ticket_res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # ACL: автор тикета, либо админ, либо helpdesk-агент (membership проверяем
    # по БД — единый источник правды, как require_helpdesk_agent).
    is_owner = ticket.requester_user_id == user.id
    is_admin = user.role == "admin"
    is_agent = False
    if not is_owner and not is_admin:
        agent_res = await db.execute(
            select(HelpdeskAgent.user_id).where(HelpdeskAgent.user_id == user.id)
        )
        is_agent = agent_res.first() is not None

    if not (is_owner or is_admin or is_agent):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return att, ticket


def delete_attachment_files(ticket_number: int, filenames: list[str]) -> None:
    """Удалить файлы вложений с диска при удалении тикета/сообщения (CASCADE).
    Best-effort: пропускает отсутствующие и невалидные имена."""
    directory = ticket_dir(ticket_number)
    for name in filenames:
        if not _SAFE_FILENAME_RE.match(name):
            continue
        (directory / name).unlink(missing_ok=True)


def delete_ticket_dir(ticket_number: int) -> None:
    """Удалить всю папку тикета (для archive-cleanup, Этап 5). Best-effort."""
    directory = ticket_dir(ticket_number)
    shutil.rmtree(directory, ignore_errors=True)
