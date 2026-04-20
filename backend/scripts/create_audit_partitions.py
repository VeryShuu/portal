"""
create_audit_partitions.py

Создаёт партиции таблицы audit_log на текущий + следующие N месяцев.
Запускается:
  - при деплое (python -m scripts.create_audit_partitions)
  - как ARQ-задача раз в месяц (1-го числа, 02:00)

Использование:
  python -m scripts.create_audit_partitions [--months 3]
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

import asyncpg


async def ensure_partitions(conn: asyncpg.Connection, months_ahead: int = 3) -> list[str]:
    created = []
    now = datetime.now(tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for i in range(months_ahead + 1):
        start = now + relativedelta(months=i)
        end   = start + relativedelta(months=1)
        tbl   = f"audit_log_{start.strftime('%Y_%m')}"

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
            print(f"[+] Created partition: {tbl} ({start.date()} .. {end.date()})")
        else:
            print(f"[=] Partition exists:  {tbl}")

    return created


async def drop_old_partitions(conn: asyncpg.Connection, retention_months: int = 12) -> list[str]:
    dropped = []
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
            print(f"[-] Dropped old partition: {tbl}")

    return dropped


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=3,
                        help="Создать партиции на N месяцев вперёд (default: 3)")
    parser.add_argument("--retention", type=int, default=12,
                        help="Хранить партиции N месяцев (default: 12)")
    parser.add_argument("--drop-old", action="store_true",
                        help="Удалить партиции старше --retention месяцев")
    args = parser.parse_args()

    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(pg_url)
    try:
        created = await ensure_partitions(conn, months_ahead=args.months)
        print(f"Partitions created: {len(created)}")

        if args.drop_old:
            dropped = await drop_old_partitions(conn, retention_months=args.retention)
            print(f"Partitions dropped: {len(dropped)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
