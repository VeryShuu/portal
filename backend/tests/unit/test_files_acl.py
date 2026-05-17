"""Unit-тесты Phase 5 — ACL файлового модуля (files_acl.py).

Покрытие:
- perm_gte: все комбинации уровней
- acl_base.subject_ids_for_user: user.id + keycloak_id + groups (единая реализация для всех ACL)
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

from app.services.acl_base import subject_ids_for_user
from app.services.files_acl import (
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
    cte_result = MagicMock()
    cte_result.fetchone.return_value = (perm,) if perm else None

    async def _execute(stmt, *args, **kwargs):
        return cte_result

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


# ── subject_ids_for_user (acl_base) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_subject_ids_includes_user_id():
    user = make_user()
    ids = await subject_ids_for_user(user)
    assert str(user.id) in ids


@pytest.mark.asyncio
async def test_subject_ids_includes_keycloak_id():
    user = make_user(keycloak_id="kc-uuid-123")
    ids = await subject_ids_for_user(user)
    assert "kc-uuid-123" in ids


@pytest.mark.asyncio
async def test_subject_ids_includes_groups():
    user = make_user(groups=["group-a", "group-b"])
    ids = await subject_ids_for_user(user)
    assert "group-a" in ids
    assert "group-b" in ids


@pytest.mark.asyncio
async def test_subject_ids_no_groups():
    user = make_user()
    ids = await subject_ids_for_user(user)
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

    cte_result = MagicMock()
    cte_result.fetchone.return_value = ("viewer",)

    db = MagicMock()
    db.execute = AsyncMock(return_value=cte_result)
    redis = make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == "viewer"


@pytest.mark.asyncio
async def test_resolve_no_permission():
    user = make_user()
    folder = make_folder()

    cte_result = MagicMock()
    cte_result.fetchone.return_value = None

    db = MagicMock()
    db.execute = AsyncMock(return_value=cte_result)
    redis = make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_inherits_from_parent():
    user = make_user()
    parent = make_folder()
    child = make_folder(parent_id=parent.id)

    cte_result = MagicMock()
    cte_result.fetchone.return_value = ("editor",)

    db = MagicMock()
    db.execute = AsyncMock(return_value=cte_result)
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

    cte_result = MagicMock()
    cte_result.fetchone.return_value = ("viewer",)

    db = MagicMock()
    db.execute = AsyncMock(return_value=cte_result)
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

    cte_result = MagicMock()
    cte_result.fetchone.return_value = None

    db = MagicMock()
    db.execute = AsyncMock(return_value=cte_result)
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


# ── Redis error handling ───────────────────────────────────────────────────────
# After unification with services.acl_base the cache helpers silently swallow
# Redis exceptions instead of logging — verifying the silent-failure contract
# is sufficient to guarantee no crash propagates to the caller.


@pytest.mark.asyncio
async def test_get_cached_returns_none_on_redis_error():
    from app.services.files_acl import _get_cached

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=Exception("redis down"))

    result = await _get_cached(redis, "test_key")

    assert result is None


@pytest.mark.asyncio
async def test_set_cached_swallows_redis_error():
    from app.services.files_acl import _set_cached

    redis = MagicMock()
    redis.setex = AsyncMock(side_effect=Exception("redis down"))

    # Must not raise.
    await _set_cached(redis, "test_key", "viewer")


@pytest.mark.asyncio
async def test_invalidate_folder_cache_with_db_children():
    from app.services.files_acl import invalidate_folder_cache

    redis = AsyncMock()
    folder_id = uuid.uuid4()
    child_id = uuid.uuid4()

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(child_id,)]
    db.execute = AsyncMock(return_value=mock_result)

    calls = []

    async def _mock_scan(r, pattern):
        calls.append(pattern)

    with patch("app.services.files_acl._scan_and_delete", _mock_scan):
        await invalidate_folder_cache(redis, folder_id, db=db)

    assert any(str(folder_id) in c for c in calls)
    assert any(str(child_id) in c for c in calls)


@pytest.mark.asyncio
async def test_invalidate_user_cache():
    from app.services.files_acl import invalidate_user_cache

    redis = AsyncMock()
    user_id = uuid.uuid4()

    with patch("app.services.files_acl._scan_and_delete", AsyncMock()) as mock_scan:
        await invalidate_user_cache(redis, user_id)
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_via_cte_empty_subjects():
    from app.services.files_acl import _resolve_via_cte

    db = AsyncMock()
    result = await _resolve_via_cte(db, uuid.uuid4(), [])
    assert result is None
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_batch_resolve_admin_returns_manager():
    from app.services.files_acl import batch_resolve_folder_permissions

    user = make_user(role="admin")
    f1 = make_folder()
    f2 = make_folder()
    db = AsyncMock()
    redis = AsyncMock()

    result = await batch_resolve_folder_permissions(user, [f1, f2], db, redis)
    assert result[f1.id] == "manager"
    assert result[f2.id] == "manager"


@pytest.mark.asyncio
async def test_batch_resolve_empty_folders():
    from app.services.files_acl import batch_resolve_folder_permissions

    user = make_user(role="reader")
    db = AsyncMock()
    redis = AsyncMock()

    result = await batch_resolve_folder_permissions(user, [], db, redis)
    assert result == {}


@pytest.mark.asyncio
async def test_batch_resolve_all_cached():
    from app.services.files_acl import batch_resolve_folder_permissions

    user = make_user(role="reader")
    f1 = make_folder()
    db = AsyncMock()
    redis = AsyncMock()
    redis.mget = AsyncMock(return_value=["viewer"])

    result = await batch_resolve_folder_permissions(user, [f1], db, redis)
    assert result[f1.id] == "viewer"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_batch_resolve_cached_none_value():
    from app.services.files_acl import batch_resolve_folder_permissions

    user = make_user(role="reader")
    f1 = make_folder()
    db = AsyncMock()
    redis = AsyncMock()
    redis.mget = AsyncMock(return_value=["none"])

    result = await batch_resolve_folder_permissions(user, [f1], db, redis)
    assert result[f1.id] is None


@pytest.mark.asyncio
async def test_batch_resolve_no_subject_ids():
    from app.services.files_acl import batch_resolve_folder_permissions

    user = make_user(role="reader", keycloak_id=None, groups=[])
    user.id = uuid.uuid4()
    user.keycloak_id = None
    user.keycloak_groups = []
    f1 = make_folder()
    db = AsyncMock()
    redis = AsyncMock()
    redis.mget = AsyncMock(return_value=[None])

    with patch("app.services.files_acl._subject_ids_for_user", AsyncMock(return_value=[])):
        result = await batch_resolve_folder_permissions(user, [f1], db, redis)

    assert result[f1.id] is None
