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


# ── Redis error logging ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_cached_logs_warning_on_redis_error():
    from unittest.mock import patch

    from app.services.files_acl import _get_cached

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=Exception("redis down"))

    with patch("app.services.files_acl.logger") as mock_logger:
        result = await _get_cached(redis, "test_key")

    assert result is None
    mock_logger.warning.assert_called_once()
    call_kwargs = mock_logger.warning.call_args
    assert "files_acl.cache_get_failed" in call_kwargs.args


@pytest.mark.asyncio
async def test_set_cached_logs_warning_on_redis_error():
    from unittest.mock import patch

    from app.services.files_acl import _set_cached

    redis = MagicMock()
    redis.setex = AsyncMock(side_effect=Exception("redis down"))

    with patch("app.services.files_acl.logger") as mock_logger:
        await _set_cached(redis, "test_key", "viewer")

    mock_logger.warning.assert_called_once()
    call_kwargs = mock_logger.warning.call_args
    assert "files_acl.cache_set_failed" in call_kwargs.args
