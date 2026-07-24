"""Admin endpoints for browsing and exporting the audit_log."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api import audit_repo
from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.logging import get_logger
from app.services.audit import AUDIT_QUEUE_KEY

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


_MAX_LIMIT = 200
_EXPORT_HARD_LIMIT = 100_000


def _build_filters(
    *,
    user_id: str | None,
    event_type: str | None,
    resource_type: str | None,
    ip_address: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if user_id:
        clauses.append("user_id = :user_id")
        params["user_id"] = user_id
    if event_type:
        clauses.append("event_type = :event_type")
        params["event_type"] = event_type
    if resource_type:
        clauses.append("resource_type = :resource_type")
        params["resource_type"] = resource_type
    if ip_address:
        clauses.append("host(ip_address) = :ip_address")
        params["ip_address"] = ip_address
    if date_from:
        clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("created_at < :date_to")
        params["date_to"] = date_to
    if q:
        clauses.append(
            "(coalesce(user_email,'') ILIKE :q "
            "OR coalesce(resource_title,'') ILIKE :q "
            "OR coalesce(metadata::text,'') ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@router.get("", summary="Журнал аудита (admin)")
async def list_audit_events(
    _admin: AdminDep,
    db: DbDep,
    user_id: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query(max_length=50)] = None,
    resource_type: Annotated[str | None, Query(max_length=50)] = None,
    ip_address: Annotated[str | None, Query(max_length=64)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    where, params = _build_filters(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        ip_address=ip_address,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    total = await audit_repo.count_events(db, where=where, params=params)

    rows = await audit_repo.list_events(db, where=where, params=params, limit=limit, offset=offset)

    items = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "user_id": str(r["user_id"]) if r["user_id"] else None,
                "user_email": r["user_email"],
                "resource_type": r["resource_type"],
                "resource_id": r["resource_id"],
                "resource_title": r["resource_title"],
                "ip_address": r["ip_address"],
                "user_agent": r["user_agent"],
                "metadata": r["metadata"] or {},
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )

    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


@router.get("/event-types", summary="Уникальные типы событий (admin)")
async def list_event_types(_admin: AdminDep, db: DbDep) -> list[str]:
    return await audit_repo.list_event_types(db)


@router.get("/queue/depth", summary="Размер очереди audit_queue в Redis")
async def audit_queue_depth(_admin: AdminDep, redis: RedisDep) -> dict[str, int]:
    try:
        pending = int(await redis.llen(AUDIT_QUEUE_KEY))
        processing = int(await redis.llen("audit_processing"))
    except Exception as exc:
        logger.exception("audit.queue_depth.redis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="audit_queue_unavailable",
        ) from exc
    return {"pending": pending, "processing": processing}


@router.get("/export.csv", summary="Экспорт журнала в CSV (admin)")
async def export_audit_csv(
    _admin: AdminDep,
    db: DbDep,
    user_id: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query(max_length=50)] = None,
    resource_type: Annotated[str | None, Query(max_length=50)] = None,
    ip_address: Annotated[str | None, Query(max_length=64)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    max_rows: int = Query(_EXPORT_HARD_LIMIT, ge=1, le=_EXPORT_HARD_LIMIT),
) -> StreamingResponse:
    where, params = _build_filters(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        ip_address=ip_address,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    import json as _json

    stream = await audit_repo.stream_events(db, where=where, params=params, max_rows=max_rows)

    async def _generate() -> AsyncGenerator[str, None]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "created_at",
                "event_type",
                "user_id",
                "user_email",
                "resource_type",
                "resource_id",
                "resource_title",
                "ip_address",
                "user_agent",
                "metadata",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()

        async for r in stream.mappings():
            writer.writerow(
                [
                    r["id"],
                    r["created_at"].isoformat() if r["created_at"] else "",
                    r["event_type"] or "",
                    str(r["user_id"]) if r["user_id"] else "",
                    r["user_email"] or "",
                    r["resource_type"] or "",
                    r["resource_id"] or "",
                    r["resource_title"] or "",
                    r["ip_address"] or "",
                    (r["user_agent"] or "")[:500],
                    _json.dumps(r["metadata"] or {}, ensure_ascii=False),
                ]
            )
            data = buffer.getvalue()
            if data:
                yield data
                buffer.seek(0)
                buffer.truncate()

    fname = f"audit_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
