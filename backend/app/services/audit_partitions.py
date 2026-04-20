"""
Сервис управления партициями audit_log.
Используется:
  - ARQ-задачами (app.worker.tasks.audit) — ежемесячное создание/удаление партиций
  - CLI-скриптом (backend/scripts/create_audit_partitions.py) — ручной запуск при деплое
"""
from datetime import datetime, timezone

import asyncpg
from dateutil.relativedelta import relativedelta


async def ensure_partitions(conn: asyncpg.Connection, months_ahead: int = 3) -> list[str]:
    created: list[str] = []
    now = datetime.now(tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for i in range(months_ahead + 1):
        start = now + relativedelta(months=i)
        end = start + relativedelta(months=1)
        tbl = f"audit_log_{start.strftime('%Y_%m')}"

        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = $1 AND n.nspname = 'public')",
            tbl,
        )
        if not exists:
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {tbl} "
                f"PARTITION OF audit_log "
                f"FOR VALUES FROM ($1) TO ($2)",
                start,
                end,
            )
            created.append(tbl)

    return created


async def drop_old_partitions(
    conn: asyncpg.Connection, retention_months: int = 12
) -> list[str]:
    dropped: list[str] = []
    cutoff = datetime.now(tz=timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ) - relativedelta(months=retention_months)

    rows = await conn.fetch(
        "SELECT c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname LIKE 'audit_log_%' "
        "AND c.relkind = 'r'"
    )
    for row in rows:
        tbl = row["relname"]
        try:
            year, month = int(tbl[-7:-3]), int(tbl[-2:])
            partition_date = datetime(year, month, 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            continue

        if partition_date < cutoff:
            await conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            dropped.append(tbl)

    return dropped
