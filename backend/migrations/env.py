import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import get_settings
from app.core.database import Base
import app.models

settings = get_settings()

target_metadata = Base.metadata

_configured_url = config.get_main_option("sqlalchemy.url") or ""
if not _configured_url or "placeholder" in _configured_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    from sqlalchemy import text as _text

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    # ВАЖНО: SET-ы выполняются ВНУТРИ alembic-транзакции (после configure +
    # begin_transaction), а не до неё. Иначе первый SET «autobegin»-ит
    # транзакцию на самом соединении ещё до configure → alembic считает её
    # внешней (_in_external_transaction=True), не открывает собственную
    # транзакцию (self._transaction остаётся None) и не коммитит результат.
    # Это же ломало autocommit_block() в миграциях 022/024
    # (assert self._transaction is not None → AssertionError).
    # Здесь alembic владеет транзакцией: коммитит успешные миграции сам и
    # корректно поддерживает CREATE INDEX CONCURRENTLY через autocommit_block.
    # SET без LOCAL — на уровне сессии, поэтому переживают commit внутри блока.
    with context.begin_transaction():
        connection.execute(_text("SET lock_timeout = '5s'"))
        connection.execute(_text("SET statement_timeout = '300s'"))
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # engine.connect() (а не begin()): транзакцией управляет сам alembic через
    # context.begin_transaction(), который коммитит её по завершении миграций.
    # Это обязательное условие для работы autocommit_block() — он требует, чтобы
    # alembic владел транзакцией (self._transaction is not None).
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
