"""Integration tests for bulk file operations.

Уровень: ASGI с моками внешних зависимостей (БД, Redis, NC).
Покрытие:
- Валидация: пустой / over-limit → 422
- Same folder → 422
- In-flight: повторный bulk → 409
- Bulk-delete happy path: 3 файла, NC 204 → все в `deleted`
- Bulk-delete: NC 404 → success=true, попадает в metadata.nc_404_count
- Bulk-move happy path: моки NC.move ok → moved=N
- Bulk-move name_conflict: NC 412 → попадает в failed
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_CSRF = "test-csrf-token"
_HEADERS = {"Origin": "http://test", "X-XSRF-TOKEN": _CSRF}
_COOKIES = {"XSRF-TOKEN": _CSRF}


def _make_user(role: str = "editor"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role}@portal.local",
        full_name="Test",
        role=role,
        auth_source="local",
        lang="ru",
        preferences={},
        keycloak_id=None,
        keycloak_groups=[],
    )


def _make_folder(name: str = "Test", nc_path: str = "PortalFiles/Test"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        parent_id=None,
        name=name,
        nc_path=nc_path,
        description=None,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
    _app = main_mod.app

    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.setex = AsyncMock()
    redis.lpush = AsyncMock()

    async def _aiter_empty():
        if False:
            yield
        return

    redis.scan_iter = MagicMock(return_value=_aiter_empty())
    _app.state.redis = redis

    # Disable rate limiter (return passthrough)
    from fastapi_limiter import FastAPILimiter

    async def _noop(_request, _response):
        return None

    FastAPILimiter.redis = redis
    FastAPILimiter.identifier = lambda req: "test"
    FastAPILimiter.http_callback = _noop
    FastAPILimiter.lua_sha = "test"

    return _app


def _override_user(app, user):
    from app.api.deps import get_current_user

    async def _fake_user():
        return user

    app.dependency_overrides[get_current_user] = _fake_user


def _clear_overrides(app):
    app.dependency_overrides.clear()


def _patch_module_enabled():
    return patch(
        "app.api.files._common.load_modules",
        return_value=SimpleNamespace(
            nextcloud=SimpleNamespace(enabled=True),
        ),
    )


def _patch_db_folder(folder, target_folder=None):
    """Mock _get_folder_or_404 to return given folder; target on second call."""
    folders = [folder] if target_folder is None else [folder, target_folder]
    call = {"i": 0}

    async def _fake_get(db, fid):
        f = folders[min(call["i"], len(folders) - 1)]
        call["i"] += 1
        return f

    return patch("app.api.files.files_ops._get_folder_or_404", side_effect=_fake_get)


def _patch_acl(perm: str = "editor"):
    async def _fake_require(user, folder, level, db, redis):
        return None

    return patch("app.api.files.files_ops.require_folder_permission", side_effect=_fake_require)


def _patch_invalidate():
    return patch(
        "app.api.files.files_ops.invalidate_folder_cache",
        new=AsyncMock(return_value=None),
    )


def _patch_audit():
    return patch("app.api.files.files_ops.push_audit_event", new=AsyncMock(return_value=None))


def _patch_db_dep(app):
    from app.api.deps import get_db

    async def _fake_db():
        sess = MagicMock()
        sess.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        sess.add = MagicMock()
        yield sess

    app.dependency_overrides[get_db] = _fake_db


# ─── Validation tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_empty_filenames_422(app):
    user = _make_user("editor")
    _override_user(app, user)
    with _patch_module_enabled():
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{uuid.uuid4()}/bulk-delete",
                    json={"filenames": []},
                )
            assert r.status_code == 422
        finally:
            _clear_overrides(app)


@pytest.mark.asyncio
async def test_bulk_delete_over_limit_422(app):
    user = _make_user("editor")
    _override_user(app, user)
    with _patch_module_enabled():
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{uuid.uuid4()}/bulk-delete",
                    json={"filenames": [f"f{i}.txt" for i in range(101)]},
                )
            assert r.status_code == 422
        finally:
            _clear_overrides(app)


@pytest.mark.asyncio
async def test_bulk_move_same_folder_422(app):
    user = _make_user("editor")
    _override_user(app, user)
    fid = uuid.uuid4()
    with _patch_module_enabled():
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{fid}/bulk-move",
                    json={"filenames": ["a.txt"], "target_folder_id": str(fid)},
                )
            assert r.status_code == 422
            assert "same_folder" in r.text
        finally:
            _clear_overrides(app)


# ─── Bulk-delete behavior ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_happy_path(app):
    user = _make_user("editor")
    folder = _make_folder()
    _override_user(app, user)
    _patch_db_dep(app)

    nc = MagicMock()
    nc.delete = AsyncMock(return_value=None)

    with (
        _patch_module_enabled(),
        _patch_db_folder(folder),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{folder.id}/bulk-delete",
                    json={"filenames": ["a.txt", "b.txt", "c.pdf"]},
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["deleted"]) == 3
    assert data["failed"] == []
    assert nc.delete.await_count == 3


@pytest.mark.asyncio
async def test_bulk_delete_nc_502_partial(app):
    user = _make_user("editor")
    folder = _make_folder()
    _override_user(app, user)
    _patch_db_dep(app)

    from app.services.nextcloud import NextcloudError

    nc = MagicMock()
    nc.delete = AsyncMock(side_effect=[None, NextcloudError(502, "bad gateway"), None])

    with (
        _patch_module_enabled(),
        _patch_db_folder(folder),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{folder.id}/bulk-delete",
                    json={"filenames": ["a.txt", "b.txt", "c.txt"]},
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200
    data = r.json()
    assert len(data["deleted"]) == 2
    assert len(data["failed"]) == 1
    assert data["failed"][0]["error"].startswith("nc_error:502")


@pytest.mark.asyncio
async def test_bulk_delete_nc_404_treated_as_success(app):
    user = _make_user("editor")
    folder = _make_folder()
    _override_user(app, user)
    _patch_db_dep(app)

    from app.services.nextcloud import NextcloudError

    nc = MagicMock()
    nc.delete = AsyncMock(side_effect=NextcloudError(404, "not found"))

    with (
        _patch_module_enabled(),
        _patch_db_folder(folder),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{folder.id}/bulk-delete",
                    json={"filenames": ["ghost.txt"]},
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200
    data = r.json()
    assert len(data["deleted"]) == 1
    assert data["deleted"][0]["success"] is True


@pytest.mark.asyncio
async def test_bulk_delete_invalid_names(app):
    user = _make_user("editor")
    folder = _make_folder()
    _override_user(app, user)
    _patch_db_dep(app)

    nc = MagicMock()
    nc.delete = AsyncMock()

    with (
        _patch_module_enabled(),
        _patch_db_folder(folder),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{folder.id}/bulk-delete",
                    json={"filenames": ["a\x00b.txt", "ok.txt"]},
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200
    data = r.json()
    assert len(data["deleted"]) == 1
    assert any(f["error"] == "invalid_name" for f in data["failed"])


@pytest.mark.asyncio
async def test_bulk_inflight_returns_409(app):
    user = _make_user("editor")
    folder = _make_folder()
    _override_user(app, user)
    _patch_db_dep(app)

    # Simulate Redis SETNX returning False (already in-flight).
    app.state.redis.set = AsyncMock(return_value=None)

    nc = MagicMock()
    nc.delete = AsyncMock()

    with (
        _patch_module_enabled(),
        _patch_db_folder(folder),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{folder.id}/bulk-delete",
                    json={"filenames": ["a.txt"]},
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 409
    assert "bulk_in_progress" in r.text


# ─── Bulk-move behavior ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_move_happy_path(app):
    user = _make_user("editor")
    src = _make_folder("Src", "PortalFiles/Src")
    tgt = _make_folder("Tgt", "PortalFiles/Tgt")
    _override_user(app, user)
    _patch_db_dep(app)

    nc = MagicMock()
    nc.move = AsyncMock(return_value=None)

    with (
        _patch_module_enabled(),
        _patch_db_folder(src, tgt),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{src.id}/bulk-move",
                    json={
                        "filenames": ["a.txt", "b.txt"],
                        "target_folder_id": str(tgt.id),
                    },
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["moved"]) == 2
    assert data["failed"] == []
    assert nc.move.await_count == 2


@pytest.mark.asyncio
async def test_bulk_move_name_conflict(app):
    user = _make_user("editor")
    src = _make_folder("Src", "PortalFiles/Src")
    tgt = _make_folder("Tgt", "PortalFiles/Tgt")
    _override_user(app, user)
    _patch_db_dep(app)

    from app.services.nextcloud import NextcloudError

    nc = MagicMock()
    nc.move = AsyncMock(side_effect=[None, NextcloudError(412, "precondition failed")])

    with (
        _patch_module_enabled(),
        _patch_db_folder(src, tgt),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{src.id}/bulk-move",
                    json={
                        "filenames": ["a.txt", "b.txt"],
                        "target_folder_id": str(tgt.id),
                    },
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200
    data = r.json()
    assert len(data["moved"]) == 1
    assert len(data["failed"]) == 1
    assert data["failed"][0]["error"] == "name_conflict"


@pytest.mark.asyncio
async def test_bulk_move_nc_404(app):
    user = _make_user("editor")
    src = _make_folder("Src", "PortalFiles/Src")
    tgt = _make_folder("Tgt", "PortalFiles/Tgt")
    _override_user(app, user)
    _patch_db_dep(app)

    from app.services.nextcloud import NextcloudError

    nc = MagicMock()
    nc.move = AsyncMock(side_effect=NextcloudError(404, "not found"))

    with (
        _patch_module_enabled(),
        _patch_db_folder(src, tgt),
        _patch_acl(),
        _patch_invalidate(),
        _patch_audit(),
        patch("app.api.files.files_ops.get_nc_service", return_value=nc),
    ):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", headers=_HEADERS, cookies=_COOKIES
            ) as ac:
                r = await ac.post(
                    f"/api/v1/files/folders/{src.id}/bulk-move",
                    json={
                        "filenames": ["ghost.txt"],
                        "target_folder_id": str(tgt.id),
                    },
                )
        finally:
            _clear_overrides(app)

    assert r.status_code == 200
    data = r.json()
    assert len(data["failed"]) == 1
    assert data["failed"][0]["error"] == "not_found"
