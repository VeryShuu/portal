"""Unit tests for app.api.kb.permissions endpoints.

Covers:
- POST /kb/sections/{id}/permissions: grant, reject modifying creator
- DELETE /kb/sections/{id}/permissions/{subject_id}: success, reject revoke creator
- POST /kb/articles/{id}/permissions: grant
- PATCH /kb/sections/{id}/inherit: copies parent perms when turning off
- PATCH /kb/articles/{id}/inherit: copies section perms when turning off
- GET /kb/users/search: merges keycloak users/groups + 'all users' synthetic group
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user(role: str = "editor", uid: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid or uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name=f"{role} user",
        keycloak_id=None,
    )


def _make_section(
    *, id: uuid.UUID | None = None, created_by: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None, inherit: bool = True,
) -> MagicMock:
    s = MagicMock()
    s.id = id or uuid.uuid4()
    s.parent_id = parent_id
    s.created_by = created_by
    s.inherit_permissions = inherit
    return s


def _make_article(
    *, id: uuid.UUID | None = None, created_by: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None, inherit: bool = True,
) -> MagicMock:
    a = MagicMock()
    a.id = id or uuid.uuid4()
    a.created_by = created_by
    a.section_id = section_id
    a.inherit_permissions = inherit
    a.deleted_at = None
    a.tags = []
    return a


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    return r


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin
    from app.api.kb.permissions import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    _app.dependency_overrides[require_admin] = _fake_user
    return _app


async def _request(app, method: str, url: str, *, json=None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.request(method, url, json=json)


def _perm_row(*, subject_id: str, subject_type: str, permission: str) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.subject_type = subject_type
    row.subject_id = subject_id
    row.subject_name = "Subject"
    row.permission = permission
    row.granted_by = uuid.uuid4()
    row.created_at = datetime.now(UTC)
    row.email = None
    row.is_creator = False
    return row


class TestSetSectionPermission:
    @pytest.mark.asyncio
    async def test_grant_section_permission_success(self):
        user = _make_user("manager")
        section = _make_section()
        db = _make_db()
        redis = _make_redis()

        new_perm = _perm_row(subject_id=str(uuid.uuid4()), subject_type="user", permission="editor")

        sec_res = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        insert_res = MagicMock(scalar_one=MagicMock(return_value=new_perm))
        db.execute.side_effect = [sec_res, insert_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_section_cache", AsyncMock()), \
             patch("app.api.kb.permissions.push_audit_event", AsyncMock()):
            r = await _request(
                app, "POST", f"/kb/sections/{section.id}/permissions",
                json={
                    "subject_type": "user",
                    "subject_id": str(uuid.uuid4()),
                    "subject_name": "Alice",
                    "permission": "editor",
                },
            )

        assert r.status_code == 201
        assert r.json()["permission"] == "editor"

    @pytest.mark.asyncio
    async def test_grant_section_permission_rejects_creator(self):
        user = _make_user("manager")
        creator_id = uuid.uuid4()
        section = _make_section(created_by=creator_id)
        db = _make_db()
        redis = _make_redis()

        sec_res = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        db.execute.return_value = sec_res

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()):
            r = await _request(
                app, "POST", f"/kb/sections/{section.id}/permissions",
                json={
                    "subject_type": "user",
                    "subject_id": str(creator_id),
                    "subject_name": "Creator",
                    "permission": "editor",
                },
            )
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_section_not_found(self):
        user = _make_user("manager")
        db = _make_db()
        redis = _make_redis()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        r = await _request(
            app, "POST", f"/kb/sections/{uuid.uuid4()}/permissions",
            json={
                "subject_type": "user",
                "subject_id": str(uuid.uuid4()),
                "subject_name": "X",
                "permission": "editor",
            },
        )
        assert r.status_code == 404


class TestDeleteSectionPermission:
    @pytest.mark.asyncio
    async def test_delete_section_perm_rejects_creator(self):
        user = _make_user("manager")
        creator_id = uuid.uuid4()
        section = _make_section(created_by=creator_id)
        db = _make_db()
        redis = _make_redis()
        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=section))

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()):
            r = await _request(
                app, "DELETE", f"/kb/sections/{section.id}/permissions/{creator_id}",
            )
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_section_perm_success(self):
        user = _make_user("manager")
        section = _make_section(created_by=uuid.uuid4())
        db = _make_db()
        redis = _make_redis()
        sec_res = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        del_res = MagicMock()
        db.execute.side_effect = [sec_res, del_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_section_cache", AsyncMock()), \
             patch("app.api.kb.permissions.push_audit_event", AsyncMock()):
            r = await _request(
                app, "DELETE", f"/kb/sections/{section.id}/permissions/{uuid.uuid4()}",
            )
        assert r.status_code == 204


class TestSetArticlePermission:
    @pytest.mark.asyncio
    async def test_grant_article_permission_success(self):
        user = _make_user("manager")
        article = _make_article()
        db = _make_db()
        redis = _make_redis()

        new_perm = _perm_row(subject_id=str(uuid.uuid4()), subject_type="user", permission="viewer")

        art_res = MagicMock(scalar_one_or_none=MagicMock(return_value=article))
        insert_res = MagicMock(scalar_one=MagicMock(return_value=new_perm))
        db.execute.side_effect = [art_res, insert_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_article_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_article_cache", AsyncMock()), \
             patch("app.api.kb.permissions.push_audit_event", AsyncMock()):
            r = await _request(
                app, "POST", f"/kb/articles/{article.id}/permissions",
                json={
                    "subject_type": "user",
                    "subject_id": str(uuid.uuid4()),
                    "subject_name": "Bob",
                    "permission": "viewer",
                },
            )
        assert r.status_code == 201
        assert r.json()["permission"] == "viewer"


class TestInheritToggle:
    @pytest.mark.asyncio
    async def test_section_inherit_off_copies_parent_perms(self):
        """При выключении наследования родительские permissions копируются."""
        user = _make_user("manager")
        parent_id = uuid.uuid4()
        section = _make_section(parent_id=parent_id, inherit=True)
        db = _make_db()
        redis = _make_redis()

        parent_perm = MagicMock()
        parent_perm.subject_type = "user"
        parent_perm.subject_id = str(uuid.uuid4())
        parent_perm.subject_name = "Parent User"
        parent_perm.permission = "editor"

        sec_res = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        parent_perms_res = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[parent_perm]))))
        insert_res = MagicMock()
        descendants_res = MagicMock(fetchall=MagicMock(return_value=[]))
        db.execute.side_effect = [sec_res, parent_perms_res, insert_res, descendants_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_section_cache", AsyncMock()):
            r = await _request(
                app, "PATCH", f"/kb/sections/{section.id}/inherit",
                json={"inherit_permissions": False},
            )
        assert r.status_code == 200
        assert r.json()["inherit_permissions"] is False
        # parent_perms был загружен и копия должна была быть вставлена
        assert db.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_section_inherit_on_skips_copy(self):
        """При включении наследования (был off → on) parent perms не копируются."""
        user = _make_user("manager")
        section = _make_section(parent_id=uuid.uuid4(), inherit=False)
        db = _make_db()
        redis = _make_redis()
        sec_res = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        descendants_res = MagicMock(fetchall=MagicMock(return_value=[]))
        db.execute.side_effect = [sec_res, descendants_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions.require_section_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_section_cache", AsyncMock()):
            r = await _request(
                app, "PATCH", f"/kb/sections/{section.id}/inherit",
                json={"inherit_permissions": True},
            )
        assert r.status_code == 200
        assert r.json()["inherit_permissions"] is True
        assert db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_article_inherit_off_copies_section_perms(self):
        user = _make_user("manager")
        section_id = uuid.uuid4()
        article = _make_article(section_id=section_id, inherit=True)
        db = _make_db()
        redis = _make_redis()

        sec_perm = MagicMock()
        sec_perm.subject_type = "user"
        sec_perm.subject_id = str(uuid.uuid4())
        sec_perm.subject_name = "Sec User"
        sec_perm.permission = "viewer"

        sec_perms_res = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sec_perm])))
        )
        insert_res = MagicMock()
        db.execute.side_effect = [sec_perms_res, insert_res]

        app = _build_app(user, db, redis)
        with patch("app.api.kb.permissions._get_article_or_404", AsyncMock(return_value=article)), \
             patch("app.api.kb.permissions.require_article_permission", AsyncMock()), \
             patch("app.api.kb.permissions.invalidate_article_cache", AsyncMock()):
            r = await _request(
                app, "PATCH", f"/kb/articles/{article.id}/inherit",
                json={"inherit_permissions": False},
            )
        assert r.status_code == 200
        assert r.json()["inherit_permissions"] is False


class TestSearchKbUsers:
    @pytest.mark.asyncio
    async def test_returns_kc_users_and_groups(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(
            "app.api.kb.permissions.kc_service.search_users",
            AsyncMock(return_value=[
                {"id": "u1", "firstName": "A", "lastName": "B", "email": "a@b.io"},
            ]),
        ), patch(
            "app.api.kb.permissions.kc_service.search_groups",
            AsyncMock(return_value=[{"path": "/grp", "name": "Group"}]),
        ):
            r = await _request(app, "GET", "/kb/users/search?q=ali")
        assert r.status_code == 200
        items = r.json()
        assert any(i["subject_type"] == "user" and i["subject_id"] == "u1" for i in items)
        assert any(i["subject_type"] == "group" and i["subject_name"] == "Group" for i in items)

    @pytest.mark.asyncio
    async def test_synthetic_all_users_group(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(
            "app.api.kb.permissions.kc_service.search_users",
            AsyncMock(return_value=[]),
        ), patch(
            "app.api.kb.permissions.kc_service.search_groups",
            AsyncMock(return_value=[]),
        ):
            r = await _request(app, "GET", "/kb/users/search?q=все")
        assert r.status_code == 200
        items = r.json()
        from app.services.acl_base import SYSTEM_ALL_USERS_NAME, SYSTEM_ALL_USERS_SUBJECT_ID

        assert any(
            i["subject_type"] == "group"
            and i["subject_id"] == SYSTEM_ALL_USERS_SUBJECT_ID
            and i["subject_name"] == SYSTEM_ALL_USERS_NAME
            for i in items
        )

    @pytest.mark.asyncio
    async def test_keycloak_failure_returns_502(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        with patch(
            "app.api.kb.permissions.kc_service.search_users",
            AsyncMock(side_effect=RuntimeError("kc down")),
        ):
            r = await _request(app, "GET", "/kb/users/search?q=any")
        assert r.status_code == 502
