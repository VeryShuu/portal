"""Pure data-access helpers for the audit log.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
The dynamic ``WHERE`` clause is *built* in the route (``_build_filters``) and
only its execution against the partitioned ``audit_log`` table lives here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession

_SELECT_COLUMNS = """
        SELECT id, event_type, user_id, user_email, resource_type, resource_id,
               resource_title, host(ip_address) AS ip_address, user_agent,
               metadata, created_at
        FROM audit_log"""


async def count_events(db: AsyncSession, *, where: str, params: dict[str, Any]) -> int:
    # f-string собирает только статический WHERE-фрагмент (имена колонок);
    # пользовательские данные идут через bind-параметры params.
    res = await db.execute(text(f"SELECT count(*) FROM audit_log{where}"), params)  # nosec B608
    return int(res.scalar_one())


async def list_events(
    db: AsyncSession,
    *,
    where: str,
    params: dict[str, Any],
    limit: int,
    offset: int,
) -> Sequence[RowMapping]:
    # f-string собирает только статический WHERE-фрагмент; данные через params.
    sql = f"""{_SELECT_COLUMNS}{where}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """  # nosec B608 — where статический; данные в params.
    res = await db.execute(text(sql), {**params, "limit": limit, "offset": offset})
    return res.mappings().all()


async def list_event_types(db: AsyncSession) -> list[str]:
    res = await db.execute(
        text(
            "SELECT DISTINCT event_type FROM audit_log "
            "WHERE created_at > now() - interval '90 days' "
            "ORDER BY event_type"
        )
    )
    return [r[0] for r in res.all()]


async def stream_events(
    db: AsyncSession, *, where: str, params: dict[str, Any], max_rows: int
) -> AsyncResult[Any]:
    sql = text(
        f"""{_SELECT_COLUMNS}{where}
        ORDER BY created_at DESC, id DESC
        LIMIT :max_rows
        """
    )
    return await db.stream(sql, {**params, "max_rows": max_rows})
