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

    connection.execute(_text("SET lock_timeout = '5s'"))
    connection.execute(_text("SET statement_timeout = '300s'"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # ВАЖНО: используем engine.begin() (а не engine.connect()), чтобы гарантировать
    # COMMIT внешней async-транзакции после успешного выполнения миграций.
    # При .connect() autobegin-транзакция, открытая первым SET ...,
    # отбрасывается (rollback) на выходе из контекстного менеджера, и весь
    # alembic upgrade head «теряется», несмотря на exit code 0.
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
