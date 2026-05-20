"""Admin endpoints для управления email outbox (исходящая очередь писем)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.api.deps import AdminDep, DbDep
from app.core.logging import get_logger
from app.services.email_outbox import cancel as outbox_cancel
from app.services.email_outbox import reschedule_for_retry

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/email-outbox", tags=["admin", "email-outbox"])

_MAX_LIMIT = 200

_ALLOWED_STATUSES = {"PENDING", "SENDING", "SENT", "FAILED", "DLQ", "CANCELLED"}


def _row_to_dict(r: Any) -> dict:
    return {
        "id": str(r["id"]),
        "kind": r["kind"],
        "to_email": r["to_email"],
        "subject": r["subject"],
        "status": r["status"],
        "attempts": int(r["attempts"]),
        "max_attempts": int(r["max_attempts"]),
        "next_attempt_at": r["next_attempt_at"].isoformat() if r["next_attempt_at"] else None,
        "last_error": r["last_error"],
        "last_error_type": r["last_error_type"],
        "last_error_class": r["last_error_class"],
        "related_resource_type": r["related_resource_type"],
        "related_resource_id": str(r["related_resource_id"]) if r["related_resource_id"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
    }


@router.get("", summary="Список писем в outbox")
async def list_outbox(
    _admin: AdminDep,
    db: DbDep,
    status_filter: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    kind: Annotated[str | None, Query(max_length=64)] = None,
    to_email: Annotated[str | None, Query(max_length=320)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if status_filter:
        if status_filter not in _ALLOWED_STATUSES:
            raise HTTPException(status_code=422, detail="invalid status")
        clauses.append("status = :status")
        params["status"] = status_filter
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if to_email:
        clauses.append("to_email ILIKE :to_email")
        params["to_email"] = f"%{to_email}%"
    if date_from:
        clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("created_at < :date_to")
        params["date_to"] = date_to
    if q:
        clauses.append("(subject ILIKE :q OR coalesce(last_error,'') ILIKE :q)")
        params["q"] = f"%{q}%"

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = (
        await db.execute(text(f"SELECT count(*) FROM email_outbox{where}"), params)
    ).scalar_one()

    rows = (
        (
            await db.execute(
                text(
                    f"""
                    SELECT id, kind, to_email, subject, status, attempts, max_attempts,
                           next_attempt_at, last_error, last_error_type, last_error_class,
                           related_resource_type, related_resource_id,
                           created_at, updated_at, sent_at
                    FROM email_outbox{where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**params, "limit": limit, "offset": offset},
            )
        )
        .mappings()
        .all()
    )

    counts_rows = (
        await db.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM email_outbox
                WHERE created_at > NOW() - interval '30 days'
                GROUP BY status
                """
            )
        )
    ).mappings().all()
    counts = {row["status"]: int(row["cnt"]) for row in counts_rows}

    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "counts_30d": counts,
    }


@router.get("/{outbox_id}", summary="Карточка письма в outbox")
async def get_outbox_item(
    outbox_id: uuid.UUID,
    _admin: AdminDep,
    db: DbDep,
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT id, kind, to_email, subject, body_html, body_text, payload,
                       status, attempts, max_attempts, next_attempt_at,
                       last_error, last_error_type, last_error_class,
                       related_resource_type, related_resource_id,
                       created_at, updated_at, sent_at
                FROM email_outbox
                WHERE id = :id
                """
            ),
            {"id": outbox_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    base = _row_to_dict(row)
    base["body_html"] = row["body_html"]
    base["body_text"] = row["body_text"]
    base["payload"] = row["payload"] or {}
    return base


@router.post("/{outbox_id}/retry", summary="Повторить отправку")
async def retry_outbox_item(
    outbox_id: uuid.UUID,
    _admin: AdminDep,
    db: DbDep,
    reset_attempts: Annotated[bool, Query()] = True,
) -> dict:
    updated = await reschedule_for_retry(db, outbox_id, reset_attempts=reset_attempts)
    await db.commit()
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_invalid_state")
    logger.info("email_outbox.admin_retry", outbox_id=str(outbox_id), reset=reset_attempts)
    return {"detail": "rescheduled"}


@router.post("/{outbox_id}/cancel", summary="Отменить отправку")
async def cancel_outbox_item(
    outbox_id: uuid.UUID,
    _admin: AdminDep,
    db: DbDep,
) -> dict:
    ok = await outbox_cancel(db, outbox_id)
    await db.commit()
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_invalid_state")
    logger.info("email_outbox.admin_cancel", outbox_id=str(outbox_id))
    return {"detail": "cancelled"}


@router.get("/_/stats", summary="Сводка по outbox")
async def outbox_stats(
    _admin: AdminDep,
    db: DbDep,
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM email_outbox
                GROUP BY status
                """
            )
        )
    ).mappings().all()
    counts = {r["status"]: int(r["cnt"]) for r in rows}
    oldest_pending = (
        await db.execute(
            text(
                "SELECT MIN(next_attempt_at) FROM email_outbox WHERE status = 'PENDING'"
            )
        )
    ).scalar()
    return {
        "counts": counts,
        "oldest_pending_at": oldest_pending.isoformat() if oldest_pending else None,
    }
