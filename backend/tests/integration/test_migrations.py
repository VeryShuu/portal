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
    return bool(
        asyncio.run(
            _fetchval(
                plain_url,
                f"SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                f"WHERE table_schema='public' AND table_name='{table}')",
            )
        )
    )


def _get_indexes(plain_url: str, table: str) -> set:
    return asyncio.run(
        _fetchset(
            plain_url,
            f"SELECT indexname FROM pg_indexes WHERE tablename='{table}' AND schemaname='public'",
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


def _is_partitioned(plain_url: str, table: str) -> bool:
    return bool(
        asyncio.run(
            _fetchval(
                plain_url,
                f"SELECT relkind = 'p' FROM pg_class "
                f"WHERE relname = '{table}' AND relnamespace = 'public'::regnamespace",
            )
        )
    )


def _partition_count(plain_url: str, parent_table: str) -> int:
    return int(  # type: ignore[call-overload]
        asyncio.run(
            _fetchval(
                plain_url,
                "SELECT count(*) FROM pg_inherits i "
                "JOIN pg_class c ON c.oid = i.inhparent "
                f"WHERE c.relname = '{parent_table}'",
            )
        )
        or 0
    )


def test_migrations_full_lifecycle(migration_env):
    """Весь жизненный цикл миграций: upgrade → проверки → downgrade → проверки → re-upgrade.

    Объединён в один тест, чтобы порядок шагов не зависел от pytest-randomly.
    """
    cfg, plain_url = migration_env

    command.upgrade(cfg, "head")

    assert _table_exists(plain_url, "users"), "users table must exist after upgrade head"
    assert _table_exists(plain_url, "idempotency_keys"), (
        "idempotency_keys table must exist after upgrade head"
    )

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
    columns = _get_columns(plain_url, "users")
    assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

    indexes = _get_indexes(plain_url, "users")
    assert "idx_users_keycloak" in indexes
    assert "idx_users_email_ci_active" in indexes
    assert "idx_users_dept" in indexes

    # ── news (миграции 002, 005, 006, 007, 011, 021, 027, 029) ────────────────
    assert _table_exists(plain_url, "news"), "news table must exist after upgrade head"
    assert _table_exists(plain_url, "news_versions"), "news_versions table must exist"
    news_columns = _get_columns(plain_url, "news")
    expected_news_columns = {
        "id",
        "title",
        "body",
        "body_tsvector",
        "cover_image",
        "cover_focal_x",
        "cover_focal_y",
        "target_departments",
        "target_roles",
        "categories",
        "created_at",
        "updated_at",
    }
    assert expected_news_columns.issubset(news_columns), (
        f"Missing news columns: {expected_news_columns - news_columns}"
    )

    # ── kb (миграции 008, 009, 010) ───────────────────────────────────────────
    for kb_table in (
        "kb_sections",
        "kb_articles",
        "kb_article_versions",
        "kb_tags",
        "kb_article_tags",
        "kb_article_comments",
        "kb_suggestions",
        "kb_article_feedback",
    ):
        assert _table_exists(plain_url, kb_table), f"{kb_table} must exist after upgrade head"

    # ── files (миграция 020, ADR-032) ─────────────────────────────────────────
    for files_table in ("file_folders", "file_folder_permissions"):
        assert _table_exists(plain_url, files_table), f"{files_table} must exist after upgrade head"

    # ── audit_log: партиционированная таблица (миграция 013) ─────────────────
    assert _table_exists(plain_url, "audit_log"), "audit_log parent table must exist"
    assert _is_partitioned(plain_url, "audit_log"), (
        "audit_log must be a partitioned (relkind='p') table"
    )
    assert _partition_count(plain_url, "audit_log") >= 1, (
        "audit_log must have at least one child partition created by the migration"
    )

    command.downgrade(cfg, "base")

    assert not _table_exists(plain_url, "users"), "users table must be removed after downgrade base"
    assert not _table_exists(plain_url, "news"), "news table must be removed after downgrade base"
    assert not _table_exists(plain_url, "kb_articles"), (
        "kb_articles must be removed after downgrade base"
    )
    assert not _table_exists(plain_url, "file_folders"), (
        "file_folders must be removed after downgrade base"
    )
    assert not _table_exists(plain_url, "audit_log"), (
        "audit_log must be removed after downgrade base"
    )

    command.upgrade(cfg, "head")

    assert _table_exists(plain_url, "users"), "users table must exist after re-upgrade"
    assert _table_exists(plain_url, "news"), "news table must exist after re-upgrade"
    assert _table_exists(plain_url, "kb_articles"), "kb_articles must exist after re-upgrade"
    assert _table_exists(plain_url, "file_folders"), "file_folders must exist after re-upgrade"
    assert _is_partitioned(plain_url, "audit_log"), (
        "audit_log must remain partitioned after re-upgrade"
    )


@pytest.fixture
def _at_head(migration_env):
    """Гарантирует, что перед тестом БД на ревизии head (для параметризованных
    round-trip тестов, чтобы порядок выполнения не влиял)."""
    from alembic.script import ScriptDirectory

    cfg, plain_url = migration_env
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()

    async def _current() -> str | None:
        conn = await asyncpg.connect(plain_url)
        try:
            return await conn.fetchval("SELECT version_num FROM alembic_version")
        except asyncpg.exceptions.UndefinedTableError:
            return None
        finally:
            await conn.close()

    if asyncio.run(_current()) != head_rev:
        command.upgrade(cfg, "head")
    return cfg, plain_url, head_rev


def _all_revisions(migration_env) -> list[str]:
    from alembic.script import ScriptDirectory

    cfg, _ = migration_env
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()
    assert head_rev is not None
    return [r.revision for r in script.walk_revisions(base="base", head=head_rev)]


def pytest_generate_tests(metafunc):
    """Параметризация test_migration_revision_round_trip по всем ревизиям.

    Делаем здесь, а не через @pytest.mark.parametrize, чтобы получить список
    из живого ScriptDirectory без поднятия контейнера (script_location доступен
    относительно backend/).
    """
    if "revision" in metafunc.fixturenames:
        from alembic.config import Config as _Config
        from alembic.script import ScriptDirectory as _ScriptDirectory

        _cfg = _Config()
        _cfg.set_main_option("script_location", "migrations")
        _script = _ScriptDirectory.from_config(_cfg)
        _head = _script.get_current_head()
        revs = [r.revision for r in _script.walk_revisions(base="base", head=_head)]
        metafunc.parametrize("revision", revs, ids=revs)


def test_migration_revision_round_trip(_at_head, revision):
    """Round-trip каждой ревизии: head → downgrade до revision-1 → upgrade head.

    Параметризованная версия test_migrations_stepwise_down_up для понятных
    сообщений об ошибках (имя теста сразу указывает на упавшую ревизию).
    """
    cfg, plain_url, head_rev = _at_head

    async def _current() -> str | None:
        conn = await asyncpg.connect(plain_url)
        try:
            return await conn.fetchval("SELECT version_num FROM alembic_version")
        except asyncpg.exceptions.UndefinedTableError:
            return None
        finally:
            await conn.close()

    # Откатываемся до revision-1 (downgrade срабатывает у самой revision)
    command.downgrade(cfg, f"{revision}-1")
    assert asyncio.run(_current()) != revision, (
        f"downgrade past {revision} must move alembic_version below it"
    )

    # Накатываем обратно по одной ревизии, проходя через revision
    command.upgrade(cfg, revision)
    assert asyncio.run(_current()) == revision, f"upgrade to {revision} did not land at it"

    command.upgrade(cfg, "head")
    assert asyncio.run(_current()) == head_rev, "must end at head after round-trip"


def test_migrations_stepwise_down_up(migration_env):
    """Пошаговый rollback и накат каждой ревизии (REVIEW-2.5).

    Гарантирует, что любая отдельная ревизия может быть откачена
    и снова применена. Это страхует от ситуации «downgrade в production
    падает на конкретной ревизии», которую не ловит downgrade base → head.

    Шаги:
      1. upgrade head
      2. для каждой ревизии (в обратном порядке): downgrade -1 → upgrade +1
      3. финальный alembic_version == head
    """
    from alembic.script import ScriptDirectory

    cfg, plain_url = migration_env

    command.upgrade(cfg, "head")

    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()
    assert head_rev is not None, "alembic head must be resolvable"

    revs = [r.revision for r in script.walk_revisions(base="base", head=head_rev)]

    async def _current() -> str | None:
        conn = await asyncpg.connect(plain_url)
        try:
            return await conn.fetchval("SELECT version_num FROM alembic_version")
        finally:
            await conn.close()

    for rev in revs:
        assert asyncio.run(_current()) == rev, f"expected to be at {rev} before stepwise check"
        # Проверяем, что ревизия откатывается и снова накатывается по одному шагу.
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "+1")
        assert asyncio.run(_current()) == rev, (
            f"upgrade +1 must return to {rev} (stepwise round-trip failed)"
        )
        # Спускаемся на шаг вниз, чтобы проверить следующую (родительскую) ревизию.
        command.downgrade(cfg, "-1")

    # После прохода по всем ревизиям мы у base — восстанавливаем head.
    command.upgrade(cfg, "head")
    assert asyncio.run(_current()) == head_rev, "final version must be head"
