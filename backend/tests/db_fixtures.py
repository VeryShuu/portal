"""Shared DB fixtures for tests that need real PostgreSQL.

Изначально жили в ``tests/integration/conftest.py``. Вынесены в отдельный модуль,
чтобы их можно было импортировать и в ``tests/unit/`` для пометки
``@pytest.mark.unit_with_db`` (см. REVIEW-2.1: поэтапный перенос mock-heavy
unit-тестов на реальную БД).

Все фикстуры пропускают тест через ``pytest.skip``, если ``INTEGRATION_DB`` не
выставлен в true — это значит, что в обычном unit-прогоне они безопасны.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio


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

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": "30000"}},
    )

    conn = await engine.connect()
    await conn.begin()
    savepoint = await conn.begin_nested()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

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
    from app.core.security import hash_password
    from app.models.user import User

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
