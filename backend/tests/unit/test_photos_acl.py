"""Unit-тесты services/photos_acl.py (Фаза 3.4).

Покрытие:
- perm_gte: None → False / viewer vs viewer / uploader vs manager / manager vs viewer
- _cache_key: format
- resolve_folder_permission: admin shortcut / created_by shortcut / cached / CTE hit / CTE miss (None)
- resolve_photo_permission: admin / uploaded_by / folder lookup / no folder
- require_folder_permission: pass (perm ok) / 403 (perm not ok)
- require_photo_permission: pass / 403
- filter_accessible_folders: admin returns all / filters out inaccessible
- filter_accessible_folders_with_perm: admin gets manager / returns (folder, perm) pairs
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_user(role: str = "reader", user_id: uuid.UUID | None = None) -> MagicMock:
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.role = role
    return u


def _make_folder(
    folder_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = folder_id or uuid.uuid4()
    f.created_by = created_by or uuid.uuid4()
    return f


def _make_photo(
    photo_id: uuid.UUID | None = None,
    uploaded_by: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
) -> MagicMock:
    p = MagicMock()
    p.id = photo_id or uuid.uuid4()
    p.uploaded_by = uploaded_by or uuid.uuid4()
    p.folder_id = folder_id or uuid.uuid4()
    return p


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    return redis


# ── perm_gte ──────────────────────────────────────────────────────────────────


def test_perm_gte_none_returns_false():
    from app.services.photos_acl import perm_gte

    assert perm_gte(None, "viewer") is False


def test_perm_gte_viewer_vs_viewer():
    from app.services.photos_acl import perm_gte

    assert perm_gte("viewer", "viewer") is True


def test_perm_gte_uploader_vs_viewer():
    from app.services.photos_acl import perm_gte

    assert perm_gte("uploader", "viewer") is True


def test_perm_gte_manager_vs_uploader():
    from app.services.photos_acl import perm_gte

    assert perm_gte("manager", "uploader") is True


def test_perm_gte_viewer_vs_manager_false():
    from app.services.photos_acl import perm_gte

    assert perm_gte("viewer", "manager") is False


def test_perm_gte_uploader_vs_manager_false():
    from app.services.photos_acl import perm_gte

    assert perm_gte("uploader", "manager") is False


def test_perm_gte_unknown_perm_false():
    from app.services.photos_acl import perm_gte

    assert perm_gte("unknown", "viewer") is False


# ── _cache_key ────────────────────────────────────────────────────────────────


def test_cache_key_format():
    from app.services.photos_acl import _cache_key

    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    folder_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    key = _cache_key(user_id, folder_id, "3")
    assert key == f"photo_acl:{user_id}:{folder_id}:v3"


# ── resolve_folder_permission ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_folder_permission_admin_shortcut():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_folder_permission

    user = _make_user(role="admin")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == PERM_MANAGER


@pytest.mark.asyncio
async def test_resolve_folder_permission_created_by_shortcut():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_folder_permission

    user_id = uuid.uuid4()
    user = _make_user(role="reader", user_id=user_id)
    folder = _make_folder(created_by=user_id)
    db = _make_db()
    redis = _make_redis()

    result = await resolve_folder_permission(user, folder, db, redis)
    assert result == PERM_MANAGER


@pytest.mark.asyncio
async def test_resolve_folder_permission_uses_redis_cache():
    from app.services.photos_acl import resolve_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    with patch("app.services.photos_acl._get_cached", AsyncMock(return_value="viewer")):
        result = await resolve_folder_permission(user, folder, db, redis)

    assert result == "viewer"


@pytest.mark.asyncio
async def test_resolve_folder_permission_none_cached_returns_none():
    from app.services.photos_acl import resolve_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    with patch("app.services.photos_acl._get_cached", AsyncMock(return_value="none")):
        result = await resolve_folder_permission(user, folder, db, redis)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_folder_permission_cte_hit():
    from app.services.photos_acl import resolve_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(return_value="manager")
    db_result = MagicMock()
    db_result.fetchone = MagicMock(return_value=mock_row)
    db.execute = AsyncMock(return_value=db_result)

    with (
        patch("app.services.photos_acl._get_cached", AsyncMock(return_value=None)),
        patch("app.services.photos_acl._subject_ids_for_user", AsyncMock(return_value=["sid1"])),
        patch("app.services.photos_acl._resolve_folder_via_cte", AsyncMock(return_value="manager")),
        patch("app.services.photos_acl._set_cached", AsyncMock()),
    ):
        result = await resolve_folder_permission(user, folder, db, redis)

    assert result == "manager"


@pytest.mark.asyncio
async def test_resolve_folder_permission_cte_miss_returns_none():
    from app.services.photos_acl import resolve_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    with (
        patch("app.services.photos_acl._get_cached", AsyncMock(return_value=None)),
        patch("app.services.photos_acl._subject_ids_for_user", AsyncMock(return_value=["sid1"])),
        patch("app.services.photos_acl._resolve_folder_via_cte", AsyncMock(return_value=None)),
        patch("app.services.photos_acl._set_cached", AsyncMock()),
    ):
        result = await resolve_folder_permission(user, folder, db, redis)

    assert result is None


# ── resolve_photo_permission ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_photo_permission_admin():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_photo_permission

    user = _make_user(role="admin")
    photo = _make_photo()
    db = _make_db()
    redis = _make_redis()

    result = await resolve_photo_permission(user, photo, db, redis)
    assert result == PERM_MANAGER


@pytest.mark.asyncio
async def test_resolve_photo_permission_uploaded_by():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_photo_permission

    user_id = uuid.uuid4()
    user = _make_user(role="reader", user_id=user_id)
    photo = _make_photo(uploaded_by=user_id)
    db = _make_db()
    redis = _make_redis()

    result = await resolve_photo_permission(user, photo, db, redis)
    assert result == PERM_MANAGER


@pytest.mark.asyncio
async def test_resolve_photo_permission_no_folder_returns_none():
    from app.services.photos_acl import resolve_photo_permission

    user = _make_user(role="reader")
    photo = _make_photo()
    db = _make_db()
    redis = _make_redis()

    db_result = MagicMock()
    db_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=db_result)

    result = await resolve_photo_permission(user, photo, db, redis)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_photo_permission_delegates_to_folder():
    from app.services.photos_acl import resolve_photo_permission

    user = _make_user(role="reader")
    photo = _make_photo()
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    db_result = MagicMock()
    db_result.scalar_one_or_none = MagicMock(return_value=folder)
    db.execute = AsyncMock(return_value=db_result)

    with patch(
        "app.services.photos_acl.resolve_folder_permission", AsyncMock(return_value="uploader")
    ):
        result = await resolve_photo_permission(user, photo, db, redis)

    assert result == "uploader"


# ── require_folder_permission ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_folder_permission_passes():
    from app.services.photos_acl import require_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    with patch(
        "app.services.photos_acl.resolve_folder_permission", AsyncMock(return_value="manager")
    ):
        await require_folder_permission(user, folder, "viewer", db, redis)


@pytest.mark.asyncio
async def test_require_folder_permission_raises_403():
    from fastapi import HTTPException

    from app.services.photos_acl import require_folder_permission

    user = _make_user(role="reader")
    folder = _make_folder()
    db = _make_db()
    redis = _make_redis()

    with (
        patch("app.services.photos_acl.resolve_folder_permission", AsyncMock(return_value=None)),
        pytest.raises(HTTPException) as exc,
    ):
        await require_folder_permission(user, folder, "viewer", db, redis)
    assert exc.value.status_code == 403


# ── require_photo_permission ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_photo_permission_passes():
    from app.services.photos_acl import require_photo_permission

    user = _make_user(role="reader")
    photo = _make_photo()
    db = _make_db()
    redis = _make_redis()

    with patch(
        "app.services.photos_acl.resolve_photo_permission", AsyncMock(return_value="uploader")
    ):
        await require_photo_permission(user, photo, "viewer", db, redis)


@pytest.mark.asyncio
async def test_require_photo_permission_raises_403():
    from fastapi import HTTPException

    from app.services.photos_acl import require_photo_permission

    user = _make_user(role="reader")
    photo = _make_photo()
    db = _make_db()
    redis = _make_redis()

    with (
        patch("app.services.photos_acl.resolve_photo_permission", AsyncMock(return_value=None)),
        pytest.raises(HTTPException) as exc,
    ):
        await require_photo_permission(user, photo, "viewer", db, redis)
    assert exc.value.status_code == 403


# ── filter_accessible_folders ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_accessible_folders_admin_returns_all():
    from app.services.photos_acl import filter_accessible_folders

    user = _make_user(role="admin")
    folders = [_make_folder(), _make_folder()]
    db = _make_db()
    redis = _make_redis()

    result = await filter_accessible_folders(user, folders, db, redis)
    assert result is folders


@pytest.mark.asyncio
async def test_filter_accessible_folders_filters_inaccessible():
    from app.services.photos_acl import filter_accessible_folders

    user = _make_user(role="reader")
    f1 = _make_folder()
    f2 = _make_folder()
    db = _make_db()
    redis = _make_redis()

    batch_result = {f1.id: "viewer", f2.id: None}

    with patch(
        "app.services.photos_acl.resolve_folders_permissions_batch",
        AsyncMock(return_value=batch_result),
    ):
        result = await filter_accessible_folders(user, [f1, f2], db, redis)

    assert result == [f1]


# ── filter_accessible_folders_with_perm ───────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_accessible_folders_with_perm_admin():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import filter_accessible_folders_with_perm

    user = _make_user(role="admin")
    folders = [_make_folder(), _make_folder()]
    db = _make_db()
    redis = _make_redis()

    result = await filter_accessible_folders_with_perm(user, folders, db, redis)
    assert len(result) == 2
    for _folder, perm in result:
        assert perm == PERM_MANAGER


@pytest.mark.asyncio
async def test_filter_accessible_folders_with_perm_returns_pairs():
    from app.services.photos_acl import filter_accessible_folders_with_perm

    user = _make_user(role="reader")
    f1 = _make_folder()
    f2 = _make_folder()
    db = _make_db()
    redis = _make_redis()

    batch_result = {f1.id: "viewer", f2.id: None}

    with patch(
        "app.services.photos_acl.resolve_folders_permissions_batch",
        AsyncMock(return_value=batch_result),
    ):
        result = await filter_accessible_folders_with_perm(user, [f1, f2], db, redis)

    assert len(result) == 1
    assert result[0] == (f1, "viewer")


# ── invalidate_folder_cache ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_folder_cache_no_db():
    from app.services.photos_acl import invalidate_folder_cache

    redis = _make_redis()
    redis.incr = AsyncMock()
    folder_id = uuid.uuid4()

    await invalidate_folder_cache(redis, folder_id)
    redis.incr.assert_called_once_with(f"photo_acl_ver:{folder_id}")


@pytest.mark.asyncio
async def test_invalidate_folder_cache_with_db_and_children():
    from app.services.photos_acl import invalidate_folder_cache

    redis = _make_redis()
    redis.incr = AsyncMock()
    folder_id = uuid.uuid4()
    child_id = uuid.uuid4()

    db = _make_db()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(child_id,)]
    db.execute = AsyncMock(return_value=mock_result)

    await invalidate_folder_cache(redis, folder_id, db=db)

    redis.incr.assert_any_call(f"photo_acl_ver:{folder_id}")
    redis.incr.assert_any_call(f"photo_acl_ver:{child_id}")


@pytest.mark.asyncio
async def test_invalidate_folder_cache_swallows_exception():
    from app.services.photos_acl import invalidate_folder_cache

    redis = _make_redis()
    redis.incr = AsyncMock(side_effect=RuntimeError("boom"))
    folder_id = uuid.uuid4()

    await invalidate_folder_cache(redis, folder_id)


@pytest.mark.asyncio
async def test_invalidate_user_cache():
    from app.services.photos_acl import invalidate_user_cache

    redis = _make_redis()
    user_id = uuid.uuid4()

    with patch("app.services.photos_acl._scan_and_delete", AsyncMock()) as mock_scan:
        await invalidate_user_cache(redis, user_id)
        mock_scan.assert_called_once_with(redis, f"photo_acl:{user_id}:*")


# ── _resolve_folder_via_cte ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_folder_via_cte_no_subject_ids():
    from app.services.photos_acl import _resolve_folder_via_cte

    db = _make_db()
    result = await _resolve_folder_via_cte(db, uuid.uuid4(), [])
    assert result is None
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_folder_via_cte_with_permission():
    from app.services.photos_acl import _resolve_folder_via_cte

    db = _make_db()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("viewer",)
    db.execute = AsyncMock(return_value=mock_result)

    result = await _resolve_folder_via_cte(db, uuid.uuid4(), ["uid-1", "group-1"])
    assert result == "viewer"


@pytest.mark.asyncio
async def test_resolve_folder_via_cte_no_rows():
    from app.services.photos_acl import _resolve_folder_via_cte

    db = _make_db()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    result = await _resolve_folder_via_cte(db, uuid.uuid4(), ["uid-1"])
    assert result is None


# ── resolve_folders_permissions_batch ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_folders_permissions_batch_admin():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_folders_permissions_batch

    user = _make_user(role="admin")
    f1 = _make_folder()
    f2 = _make_folder()
    db = _make_db()
    redis = _make_redis()

    res = await resolve_folders_permissions_batch(user, [f1, f2], db, redis)
    assert res == {f1.id: PERM_MANAGER, f2.id: PERM_MANAGER}


@pytest.mark.asyncio
async def test_resolve_folders_permissions_batch_owner():
    from app.core.constants import PERM_MANAGER
    from app.services.photos_acl import resolve_folders_permissions_batch

    uid = uuid.uuid4()
    user = _make_user(user_id=uid)
    f1 = _make_folder(created_by=uid)
    f2 = _make_folder(created_by=uid)
    db = _make_db()
    redis = _make_redis()

    res = await resolve_folders_permissions_batch(user, [f1, f2], db, redis)
    assert res == {f1.id: PERM_MANAGER, f2.id: PERM_MANAGER}


@pytest.mark.asyncio
async def test_resolve_folders_permissions_batch_cached():
    from app.services.photos_acl import resolve_folders_permissions_batch

    uid = uuid.uuid4()
    user = _make_user(user_id=uid)
    f1 = _make_folder()
    f2 = _make_folder()

    db = _make_db()
    redis = _make_redis()
    redis.mget = AsyncMock(side_effect=[[b"1", b"2"], [b"viewer", b"uploader"]])

    res = await resolve_folders_permissions_batch(user, [f1, f2], db, redis)
    assert res == {f1.id: "viewer", f2.id: "uploader"}
    assert redis.mget.call_count == 2
