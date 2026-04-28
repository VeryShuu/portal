"""Фикстуры исключительно для integration-тестов.

Все тесты в этом каталоге автоматически помечаются маркером `integration`
и пропускаются если не задан INTEGRATION_DB=true (или INTEGRATION_REDIS=true).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio


@pytest.fixture(scope="function")
def event_loop():
    """Function-scoped event loop override for integration tests.

    Overrides the session-scoped event_loop from the root conftest.py
    to avoid deadlocks with function-scoped async fixtures in pytest-asyncio >= 0.21.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_collection_modifyitems(config, items):
    """Авто-маркировка integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        item.add_marker(integration_marker)


@pytest_asyncio.fixture
async def real_db_session():
    """Сессия с изоляцией через SAVEPOINT/ROLLBACK.

    Каждый тест выполняется внутри SAVEPOINT, который откатывается в конце —
    данные не остаются в БД, не нужен TRUNCATE и нет конфликтов блокировок.

    Тесты могут вызывать session.flush() для получения id и проверки constraints.
    Не используйте session.commit() — он переносит изменения на уровень выше SAVEPOINT.
    """
    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"statement_timeout": "30000"},
    )

    conn = await engine.connect()
    await conn.begin()
    savepoint = await conn.begin_nested()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        await session.close()
        try:
            await savepoint.rollback()
        except Exception:
            pass
        try:
            await conn.rollback()
        except Exception:
            pass
        await conn.close()
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
