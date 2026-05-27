"""T4: тесты для account-linking логики (`_upsert_user`).

Тесты с моком БД проверяют ключевые ветки:
- email_verified=False → 403 (P1-16)
- email_verified=True + локальный пользователь → keycloak_id привязан, role сохранена
- новый Keycloak пользователь → создаётся через INSERT
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.auth import _upsert_user


def _make_existing_local_admin(email: str):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.keycloak_id = None
    user.auth_source = "local"
    user.role = "admin"
    user.password_hash = "$2b$12$abc"
    return user


def _ar(scalar_value):
    """Build an awaited execute() result mock returning given scalar."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=scalar_value)
    res.scalar_one = MagicMock(return_value=scalar_value)
    return res


@pytest.mark.asyncio
async def test_account_linking_refused_when_email_not_verified():
    """P1-16: account linking запрещён без email_verified=True."""
    db = AsyncMock()
    existing = _make_existing_local_admin("admin@portal.local")

    # 1. pg_advisory_xact_lock → no-op
    # 2. SELECT user by email → returns existing local admin
    db.execute.side_effect = [
        AsyncMock(),  # advisory lock
        _ar(existing),  # SELECT user by email
    ]

    with pytest.raises(HTTPException) as excinfo:
        await _upsert_user(
            db,
            {
                "email": "admin@portal.local",
                "full_name": "Admin",
                "keycloak_id": "kc-sub-123",
                "role": "reader",
                "_email_verified": False,
            },
        )
    assert excinfo.value.status_code == 403
    assert "Email not verified" in excinfo.value.detail


@pytest.mark.asyncio
async def test_account_linking_succeeds_when_email_verified():
    """Локальный пользователь получает keycloak_id; роль сохраняется."""
    db = AsyncMock()
    existing = _make_existing_local_admin("admin@portal.local")
    updated = MagicMock(id=existing.id, role="admin", auth_source="keycloak")

    db.execute.side_effect = [
        AsyncMock(),  # advisory lock
        _ar(existing),  # SELECT user by email
        AsyncMock(),  # UPDATE user
        _ar(updated),  # SELECT updated user
    ]

    result, _ = await _upsert_user(
        db,
        {
            "email": "admin@portal.local",
            "full_name": "Admin",
            "keycloak_id": "kc-sub-123",
            "role": "reader",  # должно игнорироваться, остаётся admin
            "_email_verified": True,
        },
    )
    assert result is updated
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_new_keycloak_user_inserted_via_upsert():
    """Если по email никого нет — выполняется INSERT ON CONFLICT по keycloak_id."""
    db = AsyncMock()

    inserted = MagicMock()
    inserted.id = uuid.uuid4()
    inserted.email = "new@company.local"
    inserted.role = "reader"

    fetch_result = MagicMock()
    fetch_result.fetchone = MagicMock(return_value=(inserted,))

    db.execute.side_effect = [
        AsyncMock(),  # advisory lock
        _ar(None),  # SELECT by email → ничего нет
        fetch_result,  # INSERT ON CONFLICT ... RETURNING
    ]

    result, _ = await _upsert_user(
        db,
        {
            "email": "new@company.local",
            "full_name": "New User",
            "keycloak_id": "kc-new",
            "role": "reader",
            "_email_verified": True,
        },
    )
    assert result is inserted


@pytest.mark.asyncio
async def test_unverified_email_for_new_user_still_creates():
    """Для нового (не существующего) email флаг email_verified не блокирует создание.

    Запрет email_verified касается ТОЛЬКО привязки к существующему локальному
    аккаунту, чтобы исключить hijack bootstrap-admin. Новые Keycloak пользователи
    могут создаваться даже без email_verified — это политика IdP.
    """
    db = AsyncMock()
    inserted = MagicMock(id=uuid.uuid4(), email="x@company.local")
    fetch_result = MagicMock()
    fetch_result.fetchone = MagicMock(return_value=(inserted,))

    db.execute.side_effect = [
        AsyncMock(),
        _ar(None),
        fetch_result,
    ]

    result, _ = await _upsert_user(
        db,
        {
            "email": "x@company.local",
            "full_name": "X",
            "keycloak_id": "kc-x",
            "role": "reader",
            "_email_verified": False,
        },
    )
    assert result is inserted


@pytest.mark.asyncio
async def test_advisory_lock_uses_email_hash():
    """P1-20: блокировка должна выполняться по hash(email) до SELECT."""
    db = AsyncMock()
    inserted = MagicMock(id=uuid.uuid4())
    fetch_result = MagicMock()
    fetch_result.fetchone = MagicMock(return_value=(inserted,))

    db.execute.side_effect = [
        AsyncMock(),
        _ar(None),
        fetch_result,
    ]

    await _upsert_user(
        db,
        {
            "email": "Lock@Test.Local",
            "full_name": "Lock",
            "keycloak_id": "kc",
            "role": "reader",
            "_email_verified": True,
        },
    )

    # First execute call should be the advisory lock query.
    first_call = db.execute.call_args_list[0]
    sql_clause = first_call.args[0]
    assert "pg_advisory_xact_lock" in str(sql_clause)
    params = first_call.args[1]
    assert "k" in params
    assert isinstance(params["k"], int)


@pytest.mark.asyncio
async def test_advisory_lock_key_deterministic_for_same_email():
    """Одинаковый email → одинаковый ключ блокировки (независимо от регистра)."""

    async def _run(email):
        db = AsyncMock()
        inserted = MagicMock(id=uuid.uuid4())
        fetch_result = MagicMock()
        fetch_result.fetchone = MagicMock(return_value=(inserted,))
        db.execute.side_effect = [AsyncMock(), _ar(None), fetch_result]
        await _upsert_user(
            db,
            {
                "email": email,
                "full_name": "U",
                "keycloak_id": "k",
                "role": "reader",
                "_email_verified": True,
            },
        )
        return db.execute.call_args_list[0].args[1]["k"]

    key_lower = await _run("User@Company.Local")
    key_upper = await _run("USER@COMPANY.LOCAL")
    key_mixed = await _run("user@company.local")

    assert key_lower == key_upper == key_mixed, "Lock key must be case-insensitive"

    other_key = await _run("other@company.local")
    assert key_lower != other_key, "Different emails must produce different lock keys"


@pytest.mark.asyncio
async def test_advisory_lock_acquired_before_select():
    """Блокировка должна выполняться ДО SELECT пользователя (порядок гарантирован)."""
    call_order = []
    db = AsyncMock()
    inserted = MagicMock(id=uuid.uuid4())
    fetch_result = MagicMock()
    fetch_result.fetchone = MagicMock(return_value=(inserted,))

    original_execute = db.execute

    async def _tracked_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "pg_advisory_xact_lock" in stmt_str:
            call_order.append("lock")
        else:
            call_order.append("sql")
        return await original_execute(stmt, *args, **kwargs)

    db.execute = _tracked_execute
    db.execute.side_effect = [AsyncMock(), _ar(None), fetch_result]
    db.execute = AsyncMock(side_effect=[AsyncMock(), _ar(None), fetch_result])

    # Re-implement with tracking via call_args_list inspection:
    await _upsert_user(
        db,
        {
            "email": "order@test.local",
            "full_name": "O",
            "keycloak_id": "kc",
            "role": "reader",
            "_email_verified": True,
        },
    )

    calls = db.execute.call_args_list
    assert len(calls) >= 2
    first_sql = str(calls[0].args[0])
    assert "pg_advisory_xact_lock" in first_sql, "Advisory lock must be the very first DB call"


@pytest.mark.asyncio
async def test_concurrent_first_login_no_duplicate():
    """4.4: Два параллельных первых логина одного Keycloak-пользователя не создают дублей.

    Симулирует реальную ситуацию: один и тот же Keycloak sub логинится дважды
    одновременно (например, двойной клик или два браузера). pg_advisory_xact_lock
    должен гарантировать, что в БД окажется ровно одна запись.

    Требует реального PostgreSQL (INTEGRATION_DB=true).
    """
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.api.auth import _upsert_user
    from app.core.config import get_settings

    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
    )

    email = f"race-{uuid.uuid4().hex[:8]}@portal.local"
    keycloak_id = str(uuid.uuid4())
    errors: list[Exception] = []
    results: list = []

    async def _login_attempt() -> None:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    user, _ = await _upsert_user(
                        session,
                        {
                            "email": email,
                            "full_name": "Race User",
                            "keycloak_id": keycloak_id,
                            "_email_verified": True,
                            "role": "reader",
                        },
                    )
                    results.append(user.id)
        except Exception as exc:
            errors.append(exc)

    await asyncio.gather(_login_attempt(), _login_attempt())

    await engine.dispose()

    assert not errors, f"Concurrent first-login raised errors (advisory lock failed?): {errors}"
    assert len(results) == 2, "Both calls should return a user object"
    assert results[0] == results[1], "Both concurrent logins must return the same user id"


@pytest.mark.asyncio
async def test_concurrent_account_linking_no_duplicate():
    """4.4 (account linking): Два параллельных Keycloak-логина на существующий локальный аккаунт.

    Без pg_advisory_xact_lock оба могли бы увидеть keycloak_id=None
    и оба войти в ветку «account linking», вызвав двойное UPDATE и двойной
    аудит-лог. С блокировкой — только один выполняет linking, второй находит
    уже привязанный аккаунт.

    Требует реального PostgreSQL (INTEGRATION_DB=true).
    """
    import asyncio
    import os

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.api.auth import _upsert_user
    from app.core.config import get_settings
    from app.models.user import User

    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
    )

    email = f"link-race-{uuid.uuid4().hex[:8]}@portal.local"
    keycloak_id = str(uuid.uuid4())

    async with AsyncSession(engine, expire_on_commit=False) as setup_session:
        async with setup_session.begin():
            from app.core.security import hash_password

            local_user = User(
                email=email,
                full_name="Local Admin",
                role="admin",
                auth_source="local",
                password_hash=hash_password("AdminPass!1"),
                keycloak_id=None,
            )
            setup_session.add(local_user)

    errors: list[Exception] = []
    results: list = []

    async def _keycloak_login() -> None:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    user, _ = await _upsert_user(
                        session,
                        {
                            "email": email,
                            "full_name": "Local Admin",
                            "keycloak_id": keycloak_id,
                            "_email_verified": True,
                            "role": "reader",
                        },
                    )
                    results.append((user.id, user.keycloak_id, user.role))
        except Exception as exc:
            errors.append(exc)

    await asyncio.gather(_keycloak_login(), _keycloak_login())

    async with AsyncSession(engine) as check_session:
        db_users = (
            (
                await check_session.execute(
                    select(User).where(User.email == email, User.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )

    async with AsyncSession(engine) as cleanup_session, cleanup_session.begin():
        for u in db_users:
            await cleanup_session.delete(u)

    await engine.dispose()

    assert not errors, f"Concurrent account linking raised errors: {errors}"
    assert len(db_users) == 1, f"Expected 1 user after linking race, got {len(db_users)}"
    assert db_users[0].keycloak_id == keycloak_id, "keycloak_id must be set after linking"
    assert db_users[0].role == "admin", (
        "Role must be preserved from local account (not overwritten by JWT)"
    )
