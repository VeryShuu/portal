"""Admin endpoints для просмотра messenger-outbox (вкладка «Очередь мессенджеров»).

Зеркало :mod:`app.api.email_outbox` поверх общей таблицы ``messenger_outbox``
(MAX + Matrix): список с фильтрами (статус/провайдер/чат/поиск/даты),
keyset-пагинация, карточка записи, ручные retry/cancel (сервисные функции
уже есть в :mod:`app.services.messenger_outbox`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api import messenger_outbox_repo as repo
from app.api._cursor_pagination import cursor_clause, decode_cursor, encode_cursor
from app.api.deps import AdminDep, DbDep
from app.core.logging import get_logger
from app.services.messenger_outbox import (
    cancel as outbox_cancel,
)
from app.services.messenger_outbox import (
    reschedule_for_retry,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/messenger-outbox", tags=["admin", "messenger-outbox"])

_MAX_LIMIT = 200

_ALLOWED_STATUSES = {"PENDING", "SENDING", "SENT", "FAILED", "DLQ", "CANCELLED"}
_ALLOWED_PROVIDERS = {"max", "matrix"}


def _like_escape(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_dict(r: Any) -> dict:
    return {
        "id": str(r["id"]),
        "provider": r["provider"],
        "chat_id": r["chat_id"],
        # Превью текста в списке; полный text — в карточке записи.
        "text_preview": (r["text"] or "")[:200],
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


@router.get("", summary="Список сообщений в messenger-outbox")
async def list_outbox(
    _admin: AdminDep,
    db: DbDep,
    status_filter: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    provider: Annotated[str | None, Query(max_length=32)] = None,
    chat_id: Annotated[str | None, Query(max_length=255)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
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
    if provider:
        if provider not in _ALLOWED_PROVIDERS:
            raise HTTPException(status_code=422, detail="invalid provider")
        clauses.append("provider = :provider")
        params["provider"] = provider
    if chat_id:
        clauses.append("chat_id ILIKE :chat_id ESCAPE '\\'")
        params["chat_id"] = f"%{_like_escape(chat_id)}%"
    if date_from:
        clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("created_at < :date_to")
        params["date_to"] = date_to
    if q:
        clauses.append(
            "(text ILIKE :q ESCAPE '\\' OR coalesce(last_error,'') ILIKE :q ESCAPE '\\')"
        )
        params["q"] = f"%{_like_escape(q)}%"

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = await repo.count_outbox(db, where=where, params=params)

    # cursor → keyset (O(log n) по ix_messenger_outbox_created_id, миграция
    # 097), иначе backward-compat OFFSET. cursor и offset взаимоисключающи.
    cursor_sql: str | None = None
    cursor_params: dict[str, Any] | None = None
    decoded = decode_cursor(cursor) if cursor else None
    if decoded is not None:
        cursor_sql, cursor_params = cursor_clause(decoded)

    rows = await repo.list_outbox(
        db,
        where=where,
        params=params,
        limit=limit,
        offset=offset,
        cursor_sql=cursor_sql,
        cursor_params=cursor_params,
    )
    counts = await repo.counts_by_status_last_30d(db)

    items = [_row_to_dict(r) for r in rows]
    next_cursor: str | None = None
    if len(items) >= limit and items:
        next_cursor = encode_cursor(rows[-1]["created_at"], items[-1]["id"])

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "counts_30d": counts,
        "next_cursor": next_cursor,
        "has_more": len(items) >= limit,
    }


@router.get("/{outbox_id}", summary="Карточка сообщения в messenger-outbox")
async def get_outbox_item(
    outbox_id: uuid.UUID,
    _admin: AdminDep,
    db: DbDep,
) -> dict:
    row = await repo.get_outbox_item(db, outbox_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    base = _row_to_dict(row)
    base["text"] = row["text"]
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_invalid_state"
        )
    logger.info("messenger_outbox.admin_retry", outbox_id=str(outbox_id), reset=reset_attempts)
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_invalid_state"
        )
    logger.info("messenger_outbox.admin_cancel", outbox_id=str(outbox_id))
    return {"detail": "cancelled"}
