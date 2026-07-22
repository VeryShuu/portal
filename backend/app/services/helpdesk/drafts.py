"""Draft-attachments service: temporary inline-images for the ticket **creation**
form, where no ``ticket_id`` exists yet (chicken-and-egg vs the inline-media
endpoint ``POST /tickets/{id}/inline-media``).

Lifecycle::

    create form ──POST /draft-attachments──▶ draft row + file on disk
        │                  <img src="/api/v1/helpdesk/draft-attachments/{id}">
        │
        └──create_ticket──▶ backfill_draft_images:
                             move file → TKT-{number}/inline/,
                             rewrite src → /tickets/{id}/inline-media/{name},
                             build HelpdeskAttachment(is_inline=True),
                             DELETE draft row (atomic in the same transaction)

    (abandoned form) ──cleanup_expired_drafts cron──▶ file + row purged
                             after HELPDESK_DRAFT_TTL_HOURS

ACL is deterministic via ``uploaded_by_user_id`` — only the owner can serve or
backfill a draft. FS layout: ``/data/helpdesk/drafts/usr-{user_id}/{filename}``.
"""

from __future__ import annotations

import contextlib
import re
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    HELPDESK_DRAFT_MAX_PER_USER,
    HELPDESK_DRAFT_TTL_HOURS,
    HELPDESK_FILES_DIR,
    HELPDESK_INLINE_IMAGE_MIMES,
)
from app.core.logging import get_logger
from app.core.uploads import stream_upload_to_path
from app.models.helpdesk import HelpdeskDraftAttachment, HelpdeskTicket
from app.models.user import User
from app.services.helpdesk.attachments import (
    _MAX_ATTACHMENT_BYTES,
    _build_attachment,
    _safe_stored_name,
    ticket_dir,
)
from app.services.helpdesk.email_images import find_img_sources, replace_img_src

logger = get_logger(__name__)

# Inline-media live under TKT-{number}/inline/ (same folder as the reply-form
# uploads in ``api/helpdesk/media.py``) so all of a ticket's inline images —
# whether from the creation form or a later reply — share one location.
_INLINE_SUBDIR = "inline"

# Draft URL served by ``GET /api/v1/helpdesk/draft-attachments/{id}``. Used by
# ``backfill_draft_images`` to recognise draft references in ``description_html``.
_DRAFT_URL_RE = re.compile(r"/api/v1/helpdesk/draft-attachments/([0-9a-fA-F-]{36})")


def draft_dir(user_id: uuid.UUID) -> Path:
    """On-disk folder for a user's draft uploads: ``/data/helpdesk/drafts/usr-{id}``."""
    return HELPDESK_FILES_DIR / "drafts" / f"usr-{user_id}"


def _draft_disk_path(draft: HelpdeskDraftAttachment) -> Path:
    """Full path of a draft's bytes, with path-traversal guard on the stored name."""
    return draft_dir(draft.uploaded_by_user_id) / draft.filename


def _ticket_inline_dir(ticket_number: int) -> Path:
    """Inline-image folder of a ticket: ``TKT-{number}/inline``.

    Mirrors ``api/helpdesk/media.py::_ticket_inline_dir`` — backfilled drafts
    land next to reply-form inline uploads, served by the same
    ``GET /tickets/{id}/inline-media/{name}`` endpoint.
    """
    return ticket_dir(ticket_number) / _INLINE_SUBDIR


async def create_draft_attachment(
    db: AsyncSession, *, user: User, file: UploadFile
) -> HelpdeskDraftAttachment:
    """Stream ``file`` into the user's draft folder and persist a metadata row.

    Enforces the per-user active-draft limit (``HELPDESK_DRAFT_MAX_PER_USER``):
    the user must finish or abandon existing drafts before uploading more. MIME
    is restricted to inline-image types (raster only — no SVG, consistent with
    the reply-form inline-media endpoint). The caller commits the transaction.
    """
    active = await db.scalar(
        select(func.count())
        .select_from(HelpdeskDraftAttachment)
        .where(HelpdeskDraftAttachment.uploaded_by_user_id == user.id)
    )
    if active is not None and active >= HELPDESK_DRAFT_MAX_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Too many draft attachments ({active}). Finish or discard the "
                f"ticket you are composing before uploading more images."
            ),
        )

    original_name = (file.filename or "image").strip() or "image"
    stored_name = _safe_stored_name(original_name)
    dest = draft_dir(user.id) / stored_name
    size, detected_mime = await stream_upload_to_path(
        file,
        dest,
        max_size=_MAX_ATTACHMENT_BYTES,
        allowed_mimes=HELPDESK_INLINE_IMAGE_MIMES,
    )

    draft = HelpdeskDraftAttachment(
        uploaded_by_user_id=user.id,
        filename=stored_name,
        original_name=original_name,
        content_type=detected_mime or file.content_type or "application/octet-stream",
        size_bytes=size,
    )
    db.add(draft)
    # ``id`` is server-generated (``gen_random_uuid()``); flush so the caller can
    # build the servable URL ``/draft-attachments/{draft.id}`` immediately.
    await db.flush()
    return draft


async def get_draft_for_user(
    db: AsyncSession, *, draft_id: uuid.UUID, user_id: uuid.UUID
) -> HelpdeskDraftAttachment | None:
    """Fetch a draft owned by ``user_id`` (for serve). Returns ``None`` if the
    draft does not exist or belongs to someone else — both map to 404 so we never
    disclose draft existence across users."""
    res = await db.execute(
        select(HelpdeskDraftAttachment).where(
            HelpdeskDraftAttachment.id == draft_id,
            HelpdeskDraftAttachment.uploaded_by_user_id == user_id,
        )
    )
    return res.scalar_one_or_none()


async def backfill_draft_images(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message_id: uuid.UUID,
    html: str,
    user: User,
) -> str | None:
    """Rewrite draft-attachment URLs in ``html`` into permanent inline-media URLs.

    For each ``<img src="/api/v1/helpdesk/draft-attachments/{id}">`` owned by
    ``user``: move the bytes from the draft folder to ``TKT-{number}/inline/``,
    create an inline ``HelpdeskAttachment`` (``is_inline=True``), rewrite the
    ``src`` to ``/api/v1/helpdesk/tickets/{ticket_id}/inline-media/{name}``, and
    delete the draft row — all within the caller's transaction (the ticket
    creation commit covers it atomically).

    Returns the rewritten HTML, or ``None`` if no draft URLs were present (so the
    caller can skip the assignment). Best-effort: a draft that is missing,
    unreadable, or owned by another user is left untouched (its ``src`` stays a
    draft URL) — the ticket is still created; the broken image shows the portal's
    standard broken-image affordance rather than aborting submission.
    """
    sources = find_img_sources(html)
    draft_ids: list[uuid.UUID] = []
    for src in sources:
        m = _DRAFT_URL_RE.search(src)
        if m:
            with contextlib.suppress(ValueError):
                draft_ids.append(uuid.UUID(m.group(1)))
    if not draft_ids:
        return None

    # Load all referenced drafts owned by this user in one query (dedup: the same
    # image may be embedded twice).
    unique_ids = list(dict.fromkeys(draft_ids))
    res = await db.execute(
        select(HelpdeskDraftAttachment).where(
            HelpdeskDraftAttachment.id.in_(unique_ids),
            HelpdeskDraftAttachment.uploaded_by_user_id == user.id,
        )
    )
    drafts = {d.id: d for d in res.scalars().all()}

    inline_dir = _ticket_inline_dir(ticket.number)
    inline_dir.mkdir(parents=True, exist_ok=True)
    new_html = html
    for draft_id in unique_ids:
        draft = drafts.get(draft_id)
        if draft is None:
            # Not owned by this user or already gone — leave src as-is.
            continue
        src = f"/api/v1/helpdesk/draft-attachments/{draft_id}"
        try:
            src_path = _draft_disk_path(draft)
            data = await _read_bytes(src_path)
        except OSError:
            logger.warning("helpdesk.draft.backfill.read_failed", draft_id=str(draft_id))
            continue
        if not data:
            continue

        inline_name = _safe_stored_name(draft.original_name)
        inline_path = inline_dir / inline_name
        try:
            async with aiofiles.open(inline_path, "wb") as out:
                await out.write(data)
        except OSError:
            logger.warning("helpdesk.draft.backfill.write_failed", path=str(inline_path))
            continue

        # Persist the image as an inline attachment of the ticket. ``is_inline``
        # marks it for the agent email ``cid:``-embed path and hides it from the
        # separate-attachments list in the message feed.
        _build_attachment(
            db,
            ticket=ticket,
            message_id=message_id,
            stored_name=inline_name,
            original_name=draft.original_name,
            content_type=draft.content_type,
            size=draft.size_bytes,
            uploaded_by_user_id=user.id,
            is_inline=True,
        )

        # Serve via the existing reply-form inline-media endpoint (URL keyed by
        # filename, not attachment id — same scheme as ``media.py`` uploads).
        new_src = f"/api/v1/helpdesk/tickets/{ticket.id}/inline-media/{inline_name}"
        new_html = replace_img_src(new_html, src, new_src)

        # Remove the draft row + its original bytes (the copy now lives inline).
        await db.delete(draft)
        _silently_unlink(src_path)

    logger.info(
        "helpdesk.draft.backfill.done",
        ticket_id=str(ticket.id),
        drafts_backfilled=len(unique_ids),
    )
    return new_html


async def cleanup_expired_drafts(db: AsyncSession) -> int:
    """Delete draft rows (and their bytes) older than ``HELPDESK_DRAFT_TTL_HOURS``.

    Run by the ``cleanup_expired_drafts_task`` cron. Best-effort: FS errors are
    logged and skipped so a single unreadable file does not block cleanup of the
    rest. Empty per-user draft folders are pruned to keep ``/data/helpdesk/drafts``
    tidy. Returns the number of drafts removed.
    """
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=HELPDESK_DRAFT_TTL_HOURS)
    res = await db.execute(
        select(HelpdeskDraftAttachment).where(HelpdeskDraftAttachment.created_at < cutoff)
    )
    removed = 0
    pruned_user_dirs: set[Path] = set()
    for draft in res.scalars().all():
        _silently_unlink(_draft_disk_path(draft))
        pruned_user_dirs.add(draft_dir(draft.uploaded_by_user_id))
        await db.delete(draft)
        removed += 1
    if removed:
        await db.flush()
        for d in pruned_user_dirs:
            _prune_if_empty(d)
        logger.info("helpdesk.draft.cleanup.done", removed=removed)
    return removed


async def _read_bytes(path: Path) -> bytes:
    async with aiofiles.open(path, "rb") as f:
        data: bytes = await f.read()
    return data


def _silently_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("helpdesk.draft.unlink_failed", path=str(path))


def _prune_if_empty(directory: Path) -> None:
    """Remove ``directory`` if it contains no files (best-effort)."""
    try:
        next(directory.rglob("*"))
    except StopIteration:
        # ``rmdir`` has no ``missing_ok`` (unlike ``unlink``) — guard manually.
        if directory.exists():
            directory.rmdir()
    except OSError:
        pass


__all__ = [
    "backfill_draft_images",
    "cleanup_expired_drafts",
    "create_draft_attachment",
    "draft_dir",
    "get_draft_for_user",
]
