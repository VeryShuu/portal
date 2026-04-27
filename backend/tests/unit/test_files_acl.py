"""Unit-тесты Phase 5 — ACL файлового модуля (files_acl.py).

Покрытие:
- perm_gte: все комбинации уровней
- _subject_ids_for_user: user.id + keycloak_id + groups
- resolve_folder_permission: admin, created_by, кэш-хит, рекурсия, нет доступа
- require_folder_permission: достаточно прав → OK, недостаточно → 403
- filter_accessible_folders: смешанный список
- invalidate_folder_cache
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.files_acl import (
    _subject_ids_for_user,
    filter_accessible_folders,
    invalidate_folder_cache,
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_user(role: str = "reader", keycloak_id: str | None = None, groups: list | None = None):
    uid = uuid.uuid4()
    return SimpleNamespace(
        id=uid,
        role=role,
        keycloak_id=keycloak_id or str(uid),
        keycloak_groups=groups or [],
    )


def make_folder(created_by=None, parent_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        parent_id=parent_id,
        created_by=created_by,
        nc_path="PortalFiles/Test",
    )


def make_redis(cached: str | None = None):
    r = MagicMock()
    r.get = AsyncMock(return_value=cached)
    r.setex = AsyncMock()
    r.scan_iter = MagicMock(return_value=_aiter([]))
    r.delete = AsyncMock()
    return r


async def _aiter(items):
    for i in items:
        yield i


def make_db(perm: str | None = None, parent_folder=None):
    db = MagicMock()
    perm_row = MagicMock()
    perm_row.fetchall.return_value = [(perm,)] if perm else []
    folder_row = MagicMock()
    folder_row.scalar_one_or_none.return_value = parent_folder

    execute_results = [perm_row, folder_row]
    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        result = execute_results[min(call_count, len(execute_results) - 1)]
        call_count += 1
        return result

    db.execute = _execute
    return db


# ── perm_gte ───────────────────────────────────────────────────────────────────

def test_perm_gte_none():
    assert perm_gte(None, "viewer") is False


def test_perm_gte_viewer_vs_viewer():
    assert perm_gte("viewer", "viewer") is True


def test_perm_gte_viewer_vs_editor():
    assert perm_gte("viewer", "editor") is False


def test_perm_gte_editor_vs_viewer():
    assert perm_gte("editor", "viewer") is True


def test_perm_gte_manager_vs_editor():
    assert perm_gte("manager", "editor") is True


def test_perm_gte_manager_vs_manager():
    assert perm_gte("manager", "manager") is True


# ── _subject_ids_for_user ──────────────────────────────────────────────────────

def test_subject_ids_includes_user_id():
    user = make_user()
    ids = _subject_ids_for_user(user)
    assert str(user.id) in ids


def test_subject_ids_includes_keycloak_id():
    user = make_user(keycloak_id="kc-uuid-123")
    ids = _subject_ids_for_user(user)
    assert "kc-uuid-123" in ids


def test_subject_ids_includes_groups():
    user = make_user(groups=["group-a", "group-b"])
    ids = _subject_ids_for_user(user)
    assert "group-a" in ids
    assert "group-b" in ids


def test_subject_ids_no_groups():
    user = make_user()
    ids = _subject_ids_for_user(user)
    assert str(user.id) in ids


# ── resolve_folder_permission ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_admin_always_manager():
    user = make_user(role="admin")
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == "manager"


@pytest.mark.asyncio
async def test_resolve_created_by_is_manager():
    user = make_user()
    folder = make_folder(created_by=user.id)
    db = MagicMock()
    redis = make_redis()
    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == "manager"


@pytest.mark.asyncio
async def test_resolve_cache_hit():
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis(cached="editor")
    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == "editor"


@pytest.mark.asyncio
async def test_resolve_cache_hit_none():
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis(cached="none")
    result = await resolve_folder_permission(user, folder, db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_direct_viewer():
    user = make_user()
    folder = make_folder()

    perm_result = MagicMock()
    perm_result.fetchall.return_value = [("viewer",)]
    folder_result = MagicMock()
    folder_result.scalar_one_or_none.return_value = None

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return perm_result
        return folder_result

    db = MagicMock()
    db.execute = _execute
    redis = make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == "viewer"


@pytest.mark.asyncio
async def test_resolve_no_permission():
    user = make_user()
    folder = make_folder()

    perm_result = MagicMock()
    perm_result.fetchall.return_value = []
    folder_result = MagicMock()
    folder_result.scalar_one_or_none.return_value = None

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return perm_result
        return folder_result

    db = MagicMock()
    db.execute = _execute
    redis = make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_inherits_from_parent():
    user = make_user()
    parent = make_folder()
    child = make_folder(parent_id=parent.id)

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count % 2 == 1:
            if call_count == 1:
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = [("editor",)]
        else:
            result.scalar_one_or_none.return_value = child if call_count == 2 else parent
        return result

    db = MagicMock()
    db.execute = _execute
    redis = make_redis()

    result = await resolve_folder_permission(user, child, db, redis)
    assert result == "editor"


# ── require_folder_permission ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_permission_ok():
    user = make_user()
    folder = make_folder(created_by=user.id)
    db = MagicMock()
    redis = make_redis()
    await require_folder_permission(user, folder, "manager", db, redis)


@pytest.mark.asyncio
async def test_require_permission_403():
    from fastapi import HTTPException
    user = make_user()
    folder = make_folder()

    perm_result = MagicMock()
    perm_result.fetchall.return_value = [("viewer",)]
    folder_result = MagicMock()
    folder_result.scalar_one_or_none.return_value = None

    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return perm_result
        return folder_result

    db = MagicMock()
    db.execute = _execute
    redis = make_redis()

    with pytest.raises(HTTPException) as exc_info:
        await require_folder_permission(user, folder, "editor", db, redis)
    assert exc_info.value.status_code == 403


# ── filter_accessible_folders ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_admin_gets_all():
    user = make_user(role="admin")
    folders = [make_folder(), make_folder(), make_folder()]
    db = MagicMock()
    redis = make_redis()
    result = await filter_accessible_folders(user, folders, db, redis)
    assert len(result) == 3
    assert all(perm == "manager" for _, perm in result)


@pytest.mark.asyncio
async def test_filter_returns_accessible_only():
    user = make_user()
    f1 = make_folder(created_by=user.id)
    f2 = make_folder()

    perm_result = MagicMock()
    perm_result.fetchall.return_value = []
    folder_result = MagicMock()
    folder_result.scalar_one_or_none.return_value = None

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = []
        result.scalar_one_or_none.return_value = None
        return result

    db = MagicMock()
    db.execute = _execute
    redis = make_redis()

    result = await filter_accessible_folders(user, [f1, f2], db, redis)
    accessible_folders = [f for f, _ in result]
    assert f1 in accessible_folders
    assert f2 not in accessible_folders


# ── invalidate_folder_cache ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_folder_cache_no_exception():
    folder_id = uuid.uuid4()
    redis = make_redis()
    await invalidate_folder_cache(redis, folder_id)
