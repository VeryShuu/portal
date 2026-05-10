"""
Integration-тесты миграций Alembic.
Требуют: testcontainers[postgres], asyncpg, alembic
Запуск занимает ~15–20 сек (поднятие контейнера PostgreSQL).
"""

import asyncio
import os
import pathlib

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.skipif(
    os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"),
    reason="INTEGRATION_DB=true required",
)


POSTGRES_IMAGE = "portal-postgres:16"


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer(POSTGRES_IMAGE) as container:
        yield container


@pytest.fixture(scope="module")
def migration_env(postgres_container):
    """Готовит БД (init.sql) и возвращает (alembic_cfg, plain_url)."""
    url = postgres_container.get_connection_url()
    asyncpg_url = url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "psycopg2", "asyncpg"
    )
    plain_url = url.replace("postgresql+psycopg2://", "postgresql://").replace("+psycopg2", "")

    init_sql = (pathlib.Path(__file__).parent.parent.parent / "migrations" / "init.sql").read_text()

    async def _run_init():
        conn = await asyncpg.connect(plain_url)
        try:
            await conn.execute(init_sql)
        finally:
            await conn.close()

    asyncio.run(_run_init())

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", asyncpg_url)
    return cfg, plain_url


async def _fetchval(plain_url: str, sql: str) -> object:
    conn = await asyncpg.connect(plain_url)
    try:
        return await conn.fetchval(sql)
    finally:
        await conn.close()


async def _fetchset(plain_url: str, sql: str, col: str) -> set:
    conn = await asyncpg.connect(plain_url)
    try:
        rows = await conn.fetch(sql)
        return {r[col] for r in rows}
    finally:
        await conn.close()


def _table_exists(plain_url: str, table: str) -> bool:
    return asyncio.run(
        _fetchval(
            plain_url,
            f"SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema='public' AND table_name='{table}')",
        )
    )


def _get_indexes(plain_url: str, table: str) -> set:
    return asyncio.run(
        _fetchset(
            plain_url,
            f"SELECT indexname FROM pg_indexes "
            f"WHERE tablename='{table}' AND schemaname='public'",
            "indexname",
        )
    )


def _get_columns(plain_url: str, table: str) -> set:
    return asyncio.run(
        _fetchset(
            plain_url,
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}'",
            "column_name",
        )
    )


def test_migrations_full_lifecycle(migration_env):
    """Весь жизненный цикл миграций: upgrade → проверки → downgrade → проверки → re-upgrade.

    Объединён в один тест, чтобы порядок шагов не зависел от pytest-randomly.
    """
    cfg, plain_url = migration_env

    command.upgrade(cfg, "head")

    assert _table_exists(plain_url, "users"), "users table must exist after upgrade head"
    assert _table_exists(plain_url, "idempotency_keys"), "idempotency_keys table must exist after upgrade head"

    expected_columns = {
        "id", "keycloak_id", "email", "full_name", "department",
        "position", "phone", "role", "avatar_url", "presence_status",
        "notify_email", "notify_inapp", "lang", "preferences",
        "created_at", "updated_at", "last_login_at",
    }
    columns = _get_columns(plain_url, "users")
    assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

    indexes = _get_indexes(plain_url, "users")
    assert "idx_users_keycloak" in indexes
    assert "idx_users_email_ci_active" in indexes
    assert "idx_users_dept" in indexes

    command.downgrade(cfg, "base")

    assert not _table_exists(plain_url, "users"), "users table must be removed after downgrade base"

    command.upgrade(cfg, "head")

    assert _table_exists(plain_url, "users"), "users table must exist after re-upgrade"
