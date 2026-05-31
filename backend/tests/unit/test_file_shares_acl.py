"""Unit-тесты пофайлового шеринга — резолвер прав (sharing.md §4).

Покрытие:
- resolve_file_share_permission: cache-hit (viewer/none), DB viewer/editor, нет subject_ids
- require_file_access: max(folder, share); только share; только folder; оба None → 403;
  admin (folder=manager); просрочка/отзыв (share=None) → fallback на folder
- invalidate_file_share_cache / invalidate_file_share_user_cache: без исключений
- _filename_hash стабилен
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.files_acl import (
    _filename_hash,
    invalidate_file_share_cache,
    invalidate_file_share_user_cache,
    require_file_access,
    resolve_file_share_permission,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_user(role: str = "reader", keycloak_id: str | None = None, groups=None):
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
    r.delete = AsyncMock()
    r.scan_iter = MagicMock(return_value=_aiter([]))
    return r


async def _aiter(items):
    for i in items:
        yield i


def make_db_with_share(perm: str | None):
    """db.execute returns a result whose fetchone() yields (perm,) or None."""
    res = MagicMock()
    res.fetchone.return_value = (perm,) if perm else None
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    return db


# ── _filename_hash ──────────────────────────────────────────────────────────────


def test_filename_hash_stable():
    assert _filename_hash("report.xlsx") == _filename_hash("report.xlsx")
    assert _filename_hash("a.txt") != _filename_hash("b.txt")


# ── resolve_file_share_permission ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_share_cache_hit_viewer():
    user = make_user()
    redis = make_redis(cached="viewer")
    db = MagicMock()
    result = await resolve_file_share_permission(user, uuid.uuid4(), "f.txt", db, redis)
    assert result == "viewer"


@pytest.mark.asyncio
async def test_resolve_share_cache_hit_none():
    user = make_user()
    redis = make_redis(cached="none")
    db = MagicMock()
    result = await resolve_file_share_permission(user, uuid.uuid4(), "f.txt", db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_share_db_editor():
    user = make_user()
    redis = make_redis(cached=None)
    db = make_db_with_share("editor")
    result = await resolve_file_share_permission(user, uuid.uuid4(), "f.txt", db, redis)
    assert result == "editor"


@pytest.mark.asyncio
async def test_resolve_share_db_no_row():
    user = make_user()
    redis = make_redis(cached=None)
    db = make_db_with_share(None)
    result = await resolve_file_share_permission(user, uuid.uuid4(), "f.txt", db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_share_no_subject_ids():
    user = make_user()
    redis = make_redis(cached=None)
    db = MagicMock()
    db.execute = AsyncMock()
    with patch("app.services.files_acl._subject_ids_for_user", AsyncMock(return_value=[])):
        result = await resolve_file_share_permission(user, uuid.uuid4(), "f.txt", db, redis)
    assert result is None
    db.execute.assert_not_called()


# ── require_file_access: max(folder, share) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_require_file_access_share_higher_than_folder():
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch("app.services.files_acl.resolve_folder_permission", AsyncMock(return_value="viewer")),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value="editor"),
        ),
    ):
        eff = await require_file_access(user, folder, "f.txt", "editor", db, redis)
    assert eff == "editor"


@pytest.mark.asyncio
async def test_require_file_access_folder_higher_than_share():
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch(
            "app.services.files_acl.resolve_folder_permission",
            AsyncMock(return_value="manager"),
        ),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value="viewer"),
        ),
    ):
        eff = await require_file_access(user, folder, "f.txt", "viewer", db, redis)
    assert eff == "manager"


@pytest.mark.asyncio
async def test_require_file_access_only_share():
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch("app.services.files_acl.resolve_folder_permission", AsyncMock(return_value=None)),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value="viewer"),
        ),
    ):
        eff = await require_file_access(user, folder, "f.txt", "viewer", db, redis)
    assert eff == "viewer"


@pytest.mark.asyncio
async def test_require_file_access_both_none_403():
    from fastapi import HTTPException

    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch("app.services.files_acl.resolve_folder_permission", AsyncMock(return_value=None)),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_file_access(user, folder, "f.txt", "viewer", db, redis)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_file_access_share_viewer_insufficient_for_editor():
    from fastapi import HTTPException

    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch("app.services.files_acl.resolve_folder_permission", AsyncMock(return_value=None)),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value="viewer"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_file_access(user, folder, "f.txt", "editor", db, redis)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_file_access_admin_folder_manager():
    user = make_user(role="admin")
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    # admin → resolve_folder_permission returns manager without DB
    with patch(
        "app.services.files_acl.resolve_file_share_permission",
        AsyncMock(return_value=None),
    ):
        eff = await require_file_access(user, folder, "f.txt", "viewer", db, redis)
    assert eff == "manager"


@pytest.mark.asyncio
async def test_require_file_access_expired_share_falls_back_to_folder():
    """Просроченная/отозванная шара → share=None; доступ только если есть folder ACL."""
    user = make_user()
    folder = make_folder()
    db = MagicMock()
    redis = make_redis()
    with (
        patch("app.services.files_acl.resolve_folder_permission", AsyncMock(return_value="viewer")),
        patch(
            "app.services.files_acl.resolve_file_share_permission",
            AsyncMock(return_value=None),
        ),
    ):
        eff = await require_file_access(user, folder, "f.txt", "viewer", db, redis)
    assert eff == "viewer"


# ── invalidation helpers ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_file_share_cache_no_exception():
    redis = make_redis()
    with patch("app.services.files_acl._scan_and_delete", AsyncMock()) as scan:
        await invalidate_file_share_cache(redis, uuid.uuid4(), "f.txt")
        scan.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_file_share_user_cache_no_exception():
    redis = make_redis()
    with patch("app.services.files_acl._scan_and_delete", AsyncMock()) as scan:
        await invalidate_file_share_user_cache(redis, uuid.uuid4())
        scan.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_file_share_cache_swallows_error():
    redis = make_redis()
    with patch(
        "app.services.files_acl._scan_and_delete",
        AsyncMock(side_effect=Exception("redis down")),
    ):
        # Must not raise.
        await invalidate_file_share_cache(redis, uuid.uuid4(), "f.txt")
