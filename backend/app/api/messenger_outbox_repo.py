"""Data-access helpers для админских messenger-outbox endpoints.

Зеркало :mod:`app.api.email_outbox_repo`: raw SQL вне HTTP-хендлеров,
динамические фильтры собираются в роуте из статического allow-list.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession


async def count_outbox(db: AsyncSession, *, where: str, params: dict[str, Any]) -> int:
    # where собирается из статического allow-list в роуте; данные в params.
    res = await db.execute(text(f"SELECT count(*) FROM messenger_outbox{where}"), params)  # nosec B608
    return int(res.scalar_one())


async def list_outbox(
    db: AsyncSession,
    *,
    where: str,
    params: dict[str, Any],
    limit: int,
    offset: int,
    cursor_sql: str | None = None,
    cursor_params: dict[str, Any] | None = None,
) -> Sequence[RowMapping]:
    """Список messenger_outbox-записей с пагинацией (keyset или OFFSET)."""
    effective_where = where
    bind: dict[str, Any] = {**params}
    if cursor_sql:
        connector = " AND " if where else " WHERE "
        effective_where = f"{where}{connector}{cursor_sql}"
        bind.update(cursor_params or {})
        pagination = "LIMIT :limit"
    else:
        bind["offset"] = offset
        pagination = "LIMIT :limit OFFSET :offset"
    bind["limit"] = limit
    sql = f"""
        SELECT id, provider, chat_id, text, status, attempts, max_attempts,
               next_attempt_at, last_error, last_error_type, last_error_class,
               related_resource_type, related_resource_id,
               created_at, updated_at, sent_at
        FROM messenger_outbox{effective_where}
        ORDER BY created_at DESC, id DESC
        {pagination}
        """  # nosec B608 — where/cursor_sql статические; данные в params.
    res = await db.execute(text(sql), bind)
    return res.mappings().all()


async def counts_by_status_last_30d(db: AsyncSession) -> dict[str, int]:
    res = await db.execute(
        text(
            """
            SELECT status, COUNT(*) AS cnt
            FROM messenger_outbox
            WHERE created_at > NOW() - interval '30 days'
            GROUP BY status
            """
        )
    )
    return {row["status"]: int(row["cnt"]) for row in res.mappings().all()}


async def get_outbox_item(db: AsyncSession, outbox_id: uuid.UUID) -> RowMapping | None:
    res = await db.execute(
        text(
            """
            SELECT id, provider, chat_id, text, payload,
                   status, attempts, max_attempts, next_attempt_at,
                   last_error, last_error_type, last_error_class,
                   related_resource_type, related_resource_id,
                   created_at, updated_at, sent_at
            FROM messenger_outbox
            WHERE id = :id
            """
        ),
        {"id": outbox_id},
    )
    return res.mappings().first()
