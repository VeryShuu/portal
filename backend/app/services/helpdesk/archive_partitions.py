"""Monthly partition management for ``helpdesk_tickets_archive`` (ТЗ §3.7).

Аналог ``app/services/audit_partitions.py::ensure_partitions``, но для
архивной таблицы helpdesk. Создаёт партиции на N месяцев вперёд через raw
``asyncpg.Connection``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
from dateutil.relativedelta import relativedelta

ARCHIVE_TABLE = "helpdesk_tickets_archive"


async def ensure_helpdesk_archive_partitions(
    conn: asyncpg.Connection, months_ahead: int = 3
) -> list[str]:
    """Создать отсутствующие месячные партиции архива на ``months_ahead`` вперёд.
    Возвращает имена созданных партиций."""
    created: list[str] = []
    now = datetime.now(tz=UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for i in range(months_ahead + 1):
        start = now + relativedelta(months=i)
        end = start + relativedelta(months=1)
        tbl = f"{ARCHIVE_TABLE}_{start.strftime('%Y_%m')}"

        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = $1 AND n.nspname = 'public')",
            tbl,
        )
        if not exists:
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {tbl}"
                f" PARTITION OF {ARCHIVE_TABLE}"
                f" FOR VALUES FROM ('{start.strftime('%Y-%m-%d')}')"
                f" TO ('{end.strftime('%Y-%m-%d')}')"
            )
            created.append(tbl)

    return created
