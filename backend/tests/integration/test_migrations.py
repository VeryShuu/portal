"""
Integration-тесты миграций Alembic.
Требуют: testcontainers[postgres], asyncpg, alembic
Запуск занимает ~15–20 сек (поднятие контейнера PostgreSQL).
"""

import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer
from alembic.config import Config
from alembic import command


POSTGRES_IMAGE = "postgres:16"


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer(POSTGRES_IMAGE) as container:
        yield container


@pytest.fixture(scope="module")
def alembic_cfg(postgres_container, tmp_path_factory):
    url = postgres_container.get_connection_url()
    asyncpg_url = url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "psycopg2", "asyncpg"
    )

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", asyncpg_url)
    return cfg, asyncpg_url


@pytest.fixture(scope="module")
def sync_url(postgres_container):
    return postgres_container.get_connection_url()


class TestMigrations:
    def test_upgrade_head_succeeds(self, alembic_cfg):
        cfg, _ = alembic_cfg
        command.upgrade(cfg, "head")

    def test_users_table_exists(self, alembic_cfg, sync_url):
        import asyncio

        async def check():
            conn = await asyncpg.connect(sync_url)
            try:
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='users')"
                )
                return result
            finally:
                await conn.close()

        exists = asyncio.get_event_loop().run_until_complete(check())
        assert exists is True

    def test_users_table_has_required_columns(self, alembic_cfg, sync_url):
        import asyncio

        expected_columns = {
            "id",
            "keycloak_id",
            "email",
            "full_name",
            "department",
            "position",
            "phone",
            "role",
            "avatar_url",
            "presence_status",
            "notify_email",
            "notify_inapp",
            "lang",
            "preferences",
            "created_at",
            "updated_at",
            "last_login_at",
        }

        async def check():
            conn = await asyncpg.connect(sync_url)
            try:
                rows = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='users'"
                )
                return {r["column_name"] for r in rows}
            finally:
                await conn.close()

        columns = asyncio.get_event_loop().run_until_complete(check())
        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

    def test_idempotency_keys_table_exists(self, alembic_cfg, sync_url):
        import asyncio

        async def check():
            conn = await asyncpg.connect(sync_url)
            try:
                return await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='idempotency_keys')"
                )
            finally:
                await conn.close()

        assert asyncio.get_event_loop().run_until_complete(check()) is True

    def test_users_indexes_exist(self, alembic_cfg, sync_url):
        import asyncio

        async def check():
            conn = await asyncpg.connect(sync_url)
            try:
                rows = await conn.fetch(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename='users' AND schemaname='public'"
                )
                return {r["indexname"] for r in rows}
            finally:
                await conn.close()

        indexes = asyncio.get_event_loop().run_until_complete(check())
        assert "idx_users_keycloak" in indexes
        assert "idx_users_email" in indexes
        assert "idx_users_dept" in indexes

    def test_downgrade_base_succeeds(self, alembic_cfg):
        cfg, _ = alembic_cfg
        command.downgrade(cfg, "base")

    def test_users_table_removed_after_downgrade(self, alembic_cfg, sync_url):
        import asyncio

        async def check():
            conn = await asyncpg.connect(sync_url)
            try:
                return await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='users')"
                )
            finally:
                await conn.close()

        assert asyncio.get_event_loop().run_until_complete(check()) is False

    def test_upgrade_again_after_downgrade(self, alembic_cfg):
        cfg, _ = alembic_cfg
        command.upgrade(cfg, "head")
