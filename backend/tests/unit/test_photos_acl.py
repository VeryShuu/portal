from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.photos_acl import (
    filter_accessible_folders,
    invalidate_folder_cache,
    perm_gte,
    require_folder_permission,
    resolve_folder_permission,
)


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
    )


def make_redis(cached: str | None = None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=cached)
    r.setex = AsyncMock()
    r.scan_iter = MagicMock(return_value=_aiter([]))
    r.delete = AsyncMock()
    return r


async def _aiter(items):
    for i in items:
        yield i


def make_db(perm: str | None = None):
    db = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = (perm,) if perm else None

    async def execute_side(stmt, params=None):
        return result

    db.execute = execute_side
    return db


class TestPermGte:
    def test_none_not_gte_viewer(self):
        assert perm_gte(None, "viewer") is False

    def test_viewer_gte_viewer(self):
        assert perm_gte("viewer", "viewer") is True

    def test_viewer_not_gte_uploader(self):
        assert perm_gte("viewer", "uploader") is False

    def test_viewer_not_gte_manager(self):
        assert perm_gte("viewer", "manager") is False

    def test_uploader_gte_viewer(self):
        assert perm_gte("uploader", "viewer") is True

    def test_uploader_gte_uploader(self):
        assert perm_gte("uploader", "uploader") is True

    def test_uploader_not_gte_manager(self):
        assert perm_gte("uploader", "manager") is False

    def test_manager_gte_viewer(self):
        assert perm_gte("manager", "viewer") is True

    def test_manager_gte_uploader(self):
        assert perm_gte("manager", "uploader") is True

    def test_manager_gte_manager(self):
        assert perm_gte("manager", "manager") is True

    def test_unknown_not_gte_viewer(self):
        assert perm_gte("unknown", "viewer") is False


class TestResolveFolderPermission:
    @pytest.mark.asyncio
    async def test_admin_always_manager(self):
        user = make_user(role="admin")
        folder = make_folder()
        db = MagicMock()
        redis = make_redis()
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result == "manager"

    @pytest.mark.asyncio
    async def test_creator_gets_manager(self):
        user = make_user(role="reader")
        folder = make_folder(created_by=user.id)
        db = MagicMock()
        redis = make_redis()
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result == "manager"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = MagicMock()
        redis = make_redis(cached="uploader")
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result == "uploader"
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_none_returns_none(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = MagicMock()
        redis = make_redis(cached="none")
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_direct_permission_returned(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm="viewer")
        redis = make_redis()
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result == "viewer"

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm=None)
        redis = make_redis()
        result = await resolve_folder_permission(user, folder, db, redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_inheritance_via_cte(self):
        user = make_user(role="reader")
        parent = make_folder()
        child = make_folder(parent_id=parent.id)
        db = make_db(perm="manager")
        redis = make_redis()
        result = await resolve_folder_permission(user, child, db, redis)
        assert result == "manager"

    @pytest.mark.asyncio
    async def test_result_cached_after_db_lookup(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm="uploader")
        redis = make_redis()
        await resolve_folder_permission(user, folder, db, redis)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[2] == "uploader"

    @pytest.mark.asyncio
    async def test_no_perm_caches_none_sentinel(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm=None)
        redis = make_redis()
        await resolve_folder_permission(user, folder, db, redis)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[2] == "none"


class TestRequireFolderPermission:
    @pytest.mark.asyncio
    async def test_sufficient_permission_ok(self):
        user = make_user(role="admin")
        folder = make_folder()
        db = MagicMock()
        redis = make_redis()
        await require_folder_permission(user, folder, "manager", db, redis)

    @pytest.mark.asyncio
    async def test_creator_can_manage(self):
        user = make_user(role="reader")
        folder = make_folder(created_by=user.id)
        db = MagicMock()
        redis = make_redis()
        await require_folder_permission(user, folder, "manager", db, redis)

    @pytest.mark.asyncio
    async def test_insufficient_raises_403(self):
        from fastapi import HTTPException

        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm=None)
        redis = make_redis()
        with pytest.raises(HTTPException) as exc_info:
            await require_folder_permission(user, folder, "viewer", db, redis)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_do_manager_action(self):
        from fastapi import HTTPException

        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm="viewer")
        redis = make_redis()
        with pytest.raises(HTTPException) as exc_info:
            await require_folder_permission(user, folder, "manager", db, redis)
        assert exc_info.value.status_code == 403


class TestFilterAccessibleFolders:
    @pytest.mark.asyncio
    async def test_admin_sees_all(self):
        user = make_user(role="admin")
        folders = [make_folder(), make_folder(), make_folder()]
        db = MagicMock()
        redis = make_redis()
        result = await filter_accessible_folders(user, folders, db, redis)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_reader_sees_only_own(self):
        user = make_user(role="reader")
        own = make_folder(created_by=user.id)
        other = make_folder()
        db = make_db(perm=None)
        redis = make_redis()
        result = await filter_accessible_folders(user, [own, other], db, redis)
        assert own in result
        assert other not in result

    @pytest.mark.asyncio
    async def test_reader_with_granted_permission(self):
        user = make_user(role="reader")
        folder = make_folder()
        db = make_db(perm="viewer")
        redis = make_redis()
        result = await filter_accessible_folders(user, [folder], db, redis)
        assert folder in result


class TestInvalidateFolderCache:
    @pytest.mark.asyncio
    async def test_no_exception_without_db(self):
        folder_id = uuid.uuid4()
        redis = make_redis()
        await invalidate_folder_cache(redis, folder_id)

    @pytest.mark.asyncio
    async def test_no_exception_with_db(self):
        folder_id = uuid.uuid4()
        redis = make_redis()
        db = make_db()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []

        async def execute_side(stmt, params=None):
            return result_mock

        db.execute = execute_side
        await invalidate_folder_cache(redis, folder_id, db)
