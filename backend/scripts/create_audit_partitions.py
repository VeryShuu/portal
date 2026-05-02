"""
CLI-обёртка для ручного создания партиций audit_log.

Запуск:
  python -m scripts.create_audit_partitions [--months 3] [--drop-old --retention 12]

Бизнес-логика вынесена в app.services.audit_partitions —
этот модуль только парсит аргументы и подключается к БД.
"""

import argparse
import asyncio
import os
import sys

import asyncpg

from app.services.audit_partitions import drop_old_partitions, ensure_partitions


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--months", type=int, default=3, help="Создать партиции на N месяцев вперёд (default: 3)"
    )
    parser.add_argument(
        "--retention", type=int, default=12, help="Хранить партиции N месяцев (default: 12)"
    )
    parser.add_argument(
        "--drop-old", action="store_true", help="Удалить партиции старше --retention месяцев"
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(pg_url)
    try:
        created = await ensure_partitions(conn, months_ahead=args.months)
        for tbl in created:
            print(f"[+] Created partition: {tbl}")
        print(f"Partitions created: {len(created)}")

        if args.drop_old:
            dropped = await drop_old_partitions(conn, retention_months=args.retention)
            for tbl in dropped:
                print(f"[-] Dropped old partition: {tbl}")
            print(f"Partitions dropped: {len(dropped)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
