"""Data-access helpers for the admin email-outbox endpoints.

Keeps raw SQL (``text(...)``) out of the HTTP route handlers. Dynamic filter
clauses are still assembled in the route from a fixed allow-list of templates
and passed here as a ready ``where`` fragment plus bound parameters.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession


async def count_outbox(db: AsyncSession, *, where: str, params: dict[str, Any]) -> int:
    res = await db.execute(text(f"SELECT count(*) FROM email_outbox{where}"), params)
    return int(res.scalar_one())


async def list_outbox(
    db: AsyncSession,
    *,
    where: str,
    params: dict[str, Any],
    limit: int,
    offset: int,
) -> Sequence[RowMapping]:
    res = await db.execute(
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
    return res.mappings().all()


async def counts_by_status_last_30d(db: AsyncSession) -> dict[str, int]:
    res = await db.execute(
        text(
            """
            SELECT status, COUNT(*) AS cnt
            FROM email_outbox
            WHERE created_at > NOW() - interval '30 days'
            GROUP BY status
            """
        )
    )
    return {row["status"]: int(row["cnt"]) for row in res.mappings().all()}


async def get_outbox_item(
    db: AsyncSession, outbox_id: uuid.UUID
) -> RowMapping | None:
    res = await db.execute(
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
    return res.mappings().first()


async def counts_by_status(db: AsyncSession) -> dict[str, int]:
    res = await db.execute(
        text(
            """
            SELECT status, COUNT(*) AS cnt
            FROM email_outbox
            GROUP BY status
            """
        )
    )
    return {row["status"]: int(row["cnt"]) for row in res.mappings().all()}


async def oldest_pending_at(db: AsyncSession) -> datetime | None:
    res = await db.execute(
        text("SELECT MIN(next_attempt_at) FROM email_outbox WHERE status = 'PENDING'")
    )
    return res.scalar()
