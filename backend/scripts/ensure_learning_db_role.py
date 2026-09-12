"""Идемпотентная синхронизация DB-роли learning_app (ТЗ learning.md §10.8).

Миграция 102 ставит пароль роли только если LEARNING_DB_PASSWORD был задан
В МОМЕНТ применения миграции; повторно alembic её не запустит. Поэтому
«добавили переменную в .env позже» без этого скрипта ломало learning-роуты:
движок переключался на роль, у которой пароль не установлен.

Вызывается из scripts/migrate.sh после ``alembic upgrade head`` при каждом
старте контура — роль (если её ещё нет) и пароль приводятся к значению из
окружения. Роль создаётся только миграцией 102/этим скриптом; гранты —
исключительно в миграциях (правило шапки 102: каждая learning-миграция
GRANT'ит роль сама).

Запуск без LEARNING_DB_PASSWORD — warning и exit 0: dev/тесты сознательно
работают на общем движке (app/core/database.py).
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROLE = "learning_app"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def ensure_role(password: str, database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            # Пароль идёт SQL-литералом (параметры в utility-выражениях
            # PostgreSQL не работают): гасим session-логирование, чтобы пароль
            # не попал в логи PostgreSQL при log_statement=ddl/all.
            await conn.execute(text("SET log_statement = 'none'"))
            await conn.execute(
                text(
                    f"DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') "
                    f"THEN CREATE ROLE {ROLE} LOGIN; END IF; END$$;"
                )
            )
            await conn.execute(text(f"ALTER ROLE {ROLE} LOGIN PASSWORD {_sql_literal(password)}"))
    finally:
        await engine.dispose()


def main() -> int:
    password = os.environ.get("LEARNING_DB_PASSWORD", "").strip()
    database_url = os.environ.get("DATABASE_URL", "")
    if not password:
        print(
            "[learning-role] LEARNING_DB_PASSWORD не задан — learning-роуты работают "
            "на общем движке, изоляция роли (ТЗ §10.8) НЕ действует",
            file=sys.stderr,
        )
        return 0
    if not database_url:
        print(
            "[learning-role] DATABASE_URL не задан — пропускаю синхронизацию роли", file=sys.stderr
        )
        return 1
    asyncio.run(ensure_role(password, database_url))
    print(f"[learning-role] пароль роли {ROLE} синхронизирован с окружением")
    return 0


if __name__ == "__main__":
    sys.exit(main())
