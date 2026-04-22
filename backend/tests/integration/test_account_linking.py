"""T4: тесты для account-linking логики (`_upsert_user`).

Тесты с моком БД проверяют ключевые ветки:
- email_verified=False → 403 (P1-16)
- email_verified=True + локальный пользователь → keycloak_id привязан, role сохранена
- новый Keycloak пользователь → создаётся через INSERT
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed in local env (CI runs in Docker)")

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
        AsyncMock(),               # advisory lock
        _ar(existing),             # SELECT user by email
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
        AsyncMock(),                    # advisory lock
        _ar(existing),                  # SELECT user by email
        AsyncMock(),                    # UPDATE user
        _ar(updated),                   # SELECT updated user
    ]

    result = await _upsert_user(
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
        AsyncMock(),       # advisory lock
        _ar(None),         # SELECT by email → ничего нет
        fetch_result,      # INSERT ON CONFLICT ... RETURNING
    ]

    result = await _upsert_user(
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

    result = await _upsert_user(
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
