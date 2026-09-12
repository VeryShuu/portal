"""Testcontainers: изоляция DB-роли learning_app (ТЗ learning.md §10.8).

Поднимает чистый Postgres, применяет миграции с заданным LEARNING_DB_PASSWORD
и проверяет фактические права роли: learning_* доступны, email_outbox —
INSERT-only, штатные таблицы и DDL — запрещены на уровне СУБД.

Как и test_migrations.py — только из ephemeral-контейнера
(scripts/run-testcontainers-tests.sh): нужен доступ к docker.sock.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from urllib.parse import urlparse

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.services.learning import account_import

pytestmark = pytest.mark.skipif(
    os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"),
    reason="INTEGRATION_DB=true required",
)

POSTGRES_IMAGE = os.environ.get("PORTAL_POSTGRES_IMAGE", "portal-postgres:16")

ROLE = "learning_app"
ROLE_PASSWORD = "learning-role-test-password-1"


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer(POSTGRES_IMAGE) as container:
        yield container


@pytest.fixture(scope="module")
def migrated_env(postgres_container):
    """Чистая БД + `alembic upgrade head` под заданным LEARNING_DB_PASSWORD.

    Возвращает (plain_url_владельца, dsn_роли).
    """
    url = postgres_container.get_connection_url()
    asyncpg_url = url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "psycopg2", "asyncpg"
    )
    plain_url = url.replace("postgresql+psycopg2://", "postgresql://").replace("+psycopg2", "")

    # Миграция 102 читает env напрямую (минуя кэшируемые Settings) —
    # выставляем до command.upgrade.
    old = os.environ.get("LEARNING_DB_PASSWORD")
    os.environ["LEARNING_DB_PASSWORD"] = ROLE_PASSWORD
    try:
        cfg = Config()
        cfg.set_main_option("script_location", "migrations")
        cfg.set_main_option("sqlalchemy.url", asyncpg_url)
        command.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("LEARNING_DB_PASSWORD", None)
        else:
            os.environ["LEARNING_DB_PASSWORD"] = old

    parts = urlparse(plain_url)
    role_dsn = (
        f"postgresql://{ROLE}:{ROLE_PASSWORD}"
        f"@{parts.hostname}:{parts.port}/{parts.path.lstrip('/')}"
    )
    return plain_url, role_dsn


async def _connect(dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(dsn)


async def _fetchval(dsn: str, sql: str, *args):
    conn = await _connect(dsn)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def _execute(dsn: str, sql: str, *args) -> None:
    conn = await _connect(dsn)
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _expect_privilege_error(dsn: str, sql: str) -> None:
    conn = await _connect(dsn)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(sql)
    finally:
        await conn.close()


def test_learning_role_isolation(migrated_env):
    owner_url, role_dsn = migrated_env

    # Роль создана миграцией и может логиниться
    assert (
        asyncio.run(
            _fetchval(owner_url, "SELECT rolcanlogin FROM pg_roles WHERE rolname = $1", ROLE)
        )
        is True
    )

    # ── learning_*: полный доступ ────────────────────────────────────────────

    async def learning_rw() -> int:
        conn = await _connect(role_dsn)
        try:
            email = f"role-{uuid.uuid4().hex[:8]}@example.com"
            await conn.execute(
                "INSERT INTO learning_accounts (email, full_name) VALUES ($1, $2)",
                email,
                "Роль Проверочная",
            )
            count = await conn.fetchval(
                "SELECT count(*) FROM learning_accounts WHERE email = $1", email
            )
            await conn.execute("UPDATE learning_accounts SET status = 'blocked' WHERE false")
            await conn.execute("DELETE FROM learning_accounts WHERE status = 'blocked'")
            return int(count)
        finally:
            await conn.close()

    assert asyncio.run(learning_rw()) == 1

    # ── коды входа (passwordless, миграция 113): RW роли learning_app ────────
    async def login_codes_rw() -> int:
        conn = await _connect(role_dsn)
        try:
            email = f"role-code-{uuid.uuid4().hex[:8]}@example.com"
            account_id = await conn.fetchval(
                "INSERT INTO learning_accounts (email, full_name) VALUES ($1, $2) RETURNING id",
                email,
                "Роль Кодовая",
            )
            await conn.execute(
                "INSERT INTO learning_login_codes (account_id, code_hash, expires_at) "
                "VALUES ($1, $2, now() + interval '10 minutes')",
                account_id,
                "a" * 64,
            )
            await conn.execute(
                "UPDATE learning_login_codes SET used_at = now() WHERE account_id = $1",
                account_id,
            )
            count = await conn.fetchval(
                "SELECT count(*) FROM learning_login_codes WHERE account_id = $1", account_id
            )
            await conn.execute("DELETE FROM learning_login_codes WHERE account_id = $1", account_id)
            await conn.execute("DELETE FROM learning_accounts WHERE id = $1", account_id)
            return int(count)
        finally:
            await conn.close()

    assert asyncio.run(login_codes_rw()) == 1

    # ── справочник категорий: RW (гранты миграции 112; 109 дала лишь SELECT —
    # POST /learning/admin/categories падал 500 на ограниченном контуре) ─────
    async def categories_rw() -> str:
        conn = await _connect(role_dsn)
        try:
            title = f"Категория {uuid.uuid4().hex[:8]}"
            cat_id = await conn.fetchval(
                "INSERT INTO learning_course_categories (title) VALUES ($1) RETURNING id",
                title,
            )
            await conn.execute(
                "UPDATE learning_course_categories SET sort_order = 7 WHERE id = $1", cat_id
            )
            await conn.execute(
                "UPDATE learning_course_categories SET deleted_at = NOW() WHERE id = $1",
                cat_id,
            )
            return await conn.fetchval(
                "SELECT title FROM learning_course_categories WHERE id = $1", cat_id
            )
        finally:
            await conn.close()

    assert asyncio.run(categories_rw()) is not None

    # ── email_outbox: INSERT + RETURNING id (грант миграции 103), но не SELECT ─
    # enqueue_outbox_email вставляет через INSERT ... RETURNING id: PostgreSQL
    # требует SELECT на возвращаемую колонку — ревью 2026-08-28. Полный SELECT
    # (и SELECT других колонок) по-прежнему запрещён: в письмах пароли (§5.2).
    async def outbox_insert_returning() -> str:
        conn = await _connect(role_dsn)
        try:
            return await conn.fetchval(
                "INSERT INTO email_outbox (kind, to_email, subject) "
                "VALUES ('learning', 'dest@example.com', 'Из роли') RETURNING id"
            )
        finally:
            await conn.close()

    assert asyncio.run(outbox_insert_returning()) is not None
    # NB: count(*) и SELECT id при column-grant допустимы (PostgreSQL требует
    # SELECT только на используемые колонки) — секретов в id/числе строк нет.
    asyncio.run(_expect_privilege_error(role_dsn, "SELECT subject FROM email_outbox LIMIT 1"))
    asyncio.run(_expect_privilege_error(role_dsn, "SELECT * FROM email_outbox LIMIT 1"))
    asyncio.run(
        _expect_privilege_error(role_dsn, "UPDATE email_outbox SET status = 'SENT' WHERE false")
    )

    # ── штатные таблицы и DDL: отказ на уровне СУБД ──────────────────────────
    asyncio.run(_expect_privilege_error(role_dsn, "SELECT count(*) FROM users"))
    asyncio.run(_expect_privilege_error(role_dsn, "SELECT count(*) FROM news"))
    asyncio.run(_expect_privilege_error(role_dsn, "SELECT count(*) FROM helpdesk_tickets"))
    asyncio.run(_expect_privilege_error(role_dsn, "CREATE TABLE role_probe (id int)"))
    asyncio.run(_expect_privilege_error(role_dsn, f"GRANT SELECT ON TABLE users TO {ROLE}"))


def test_learning_role_can_run_batch_account_import(migrated_env):
    owner_url, role_dsn = migrated_env

    async def run_import() -> tuple[int, int]:
        engine = create_async_engine(role_dsn.replace("postgresql://", "postgresql+asyncpg://"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            parsed = account_import.parse_xlsx(account_import.build_template())
            async with factory() as session:
                result = await account_import.import_accounts(session, parsed)
                await session.commit()
            return result.created, result.skipped_duplicates
        finally:
            await engine.dispose()

    # Импорт создаёт учётку под ролью learning_app; писем при импорте больше
    # нет (passwordless, миграция 113) — outbox остаётся пустым.
    assert asyncio.run(run_import()) == (1, 0)
    assert (
        asyncio.run(
            _fetchval(
                owner_url,
                "SELECT count(*) FROM email_outbox WHERE to_email = $1",
                "ivanov@example.ru",
            )
        )
        == 0
    )
