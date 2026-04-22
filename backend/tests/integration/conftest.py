"""Фикстуры исключительно для integration-тестов.

Все тесты в этом каталоге автоматически помечаются маркером `integration`
и пропускаются если не задан INTEGRATION_DB=true (или INTEGRATION_REDIS=true).
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio


def pytest_collection_modifyitems(config, items):
    """Авто-маркировка integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        item.add_marker(integration_marker)


@pytest_asyncio.fixture
async def real_db_session():
    """Полноценная сессия с COMMIT, чистится через truncate в finally.

    В отличие от `db_session` из корневого conftest — здесь мы реально коммитим
    (нужно для проверки триггеров, generated columns, partition routing).
    Очистка через TRUNCATE с CASCADE.
    """
    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        # Чистим все non-system таблицы.
        async with engine.begin() as conn:
            await conn.execute(text("""
                DO $$
                DECLARE r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT tablename FROM pg_tables
                        WHERE schemaname = 'public'
                          AND tablename NOT LIKE 'alembic_%'
                          AND tablename NOT LIKE 'audit_log_%'
                    )
                    LOOP
                        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """))
        await engine.dispose()


@pytest_asyncio.fixture
async def real_user(real_db_session):
    """Реальный пользователь в БД."""
    from app.models.user import User

    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Integration User",
        department="IT",
        role="reader",
        auth_source="local",
        password_hash=None,
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(user)
    await real_db_session.commit()
    await real_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def real_editor(real_db_session):
    from app.models.user import User

    user = User(
        email=f"editor-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Integration Editor",
        department="HR",
        role="editor",
        auth_source="local",
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(user)
    await real_db_session.commit()
    await real_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def real_admin(real_db_session):
    from app.models.user import User
    from app.core.security import hash_password

    user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Integration Admin",
        department="IT",
        role="admin",
        auth_source="local",
        password_hash=hash_password("Adm1nP@ss!"),
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(user)
    await real_db_session.commit()
    await real_db_session.refresh(user)
    return user
