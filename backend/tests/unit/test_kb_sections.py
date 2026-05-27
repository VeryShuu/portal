"""Unit-тесты api/kb/sections.py (Phase 4.4).

Покрытие:
- GET /kb/sections: пустой список / с разделами / фильтрация по perm_map
- POST /kb/sections: 201 created / parent_id не найден / slug collision (fallback)
- PUT /kb/sections/{id}: success / 404 / self-parent 422 / parent не найден / cycle / поля
- DELETE /kb/sections/{id}: success / 404 / есть дочерние / есть статьи
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

_KB_ACL = "app.api.kb.sections"


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        keycloak_id=None,
    )


def _make_section(
    *,
    id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    title: str = "Section",
    slug: str = "section",
    description: str | None = None,
    sort_order: int = 0,
    deleted_at=None,
) -> MagicMock:
    s = MagicMock()
    s.id = id or uuid.uuid4()
    s.parent_id = parent_id
    s.title = title
    s.slug = slug
    s.description = description
    s.sort_order = sort_order
    s.deleted_at = deleted_at
    s.inherit_permissions = True
    s.created_at = datetime.now(UTC)
    return s


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.expunge = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    return r


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis, require_admin
    from app.api.kb.sections import router

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


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


async def _put(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.put(url, json=json)


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


# ── GET /kb/sections ──────────────────────────────────────────────────────────


class TestGetSections:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sections(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        with patch(
            "app.api.kb.sections.batch_resolve_section_permissions",
            new_callable=AsyncMock,
            return_value={},
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/sections")

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    @pytest.mark.asyncio
    async def test_returns_sections_tree(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()
        root = _make_section(id=root_id, title="Root", slug="root")
        child = _make_section(id=child_id, parent_id=root_id, title="Child", slug="child")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [root, child]
        db.execute.return_value = mock_result

        perm_map = {root_id: "viewer", child_id: "viewer"}

        with patch(
            "app.api.kb.sections.batch_resolve_section_permissions",
            new_callable=AsyncMock,
            return_value=perm_map,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/sections")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Root"
        assert len(data["items"][0]["children"]) == 1
        assert data["items"][0]["children"][0]["title"] == "Child"

    @pytest.mark.asyncio
    async def test_excludes_sections_without_permission(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        s1_id = uuid.uuid4()
        s2_id = uuid.uuid4()
        s1 = _make_section(id=s1_id, title="Visible", slug="visible")
        s2 = _make_section(id=s2_id, title="Hidden", slug="hidden")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [s1, s2]
        db.execute.return_value = mock_result

        perm_map = {s1_id: "viewer"}

        with patch(
            "app.api.kb.sections.batch_resolve_section_permissions",
            new_callable=AsyncMock,
            return_value=perm_map,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/sections")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Visible"


# ── POST /kb/sections ─────────────────────────────────────────────────────────


class TestCreateSection:
    @pytest.mark.asyncio
    async def test_creates_section_201(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        new_section = _make_section(title="New Section", slug="new-section")

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": None}),
            MagicMock(**{"scalar_one_or_none.return_value": None}),
        ]
        db.execute.side_effect = execute_results

        async def _fake_refresh(obj):
            obj.id = new_section.id
            obj.title = "New Section"
            obj.slug = "new-section"
            obj.parent_id = None
            obj.description = None
            obj.sort_order = 0
            obj.created_at = new_section.created_at

        db.refresh.side_effect = _fake_refresh

        with patch("app.api.kb.sections.require_section_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _post(app, "/kb/sections", json={"title": "New Section"})

        assert resp.status_code == 201
        assert resp.json()["title"] == "New Section"

    @pytest.mark.asyncio
    async def test_returns_404_when_parent_not_found(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        parent_id = uuid.uuid4()

        db.execute.return_value.scalar_one_or_none.return_value = None

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/kb/sections",
            json={"title": "Child", "parent_id": str(parent_id)},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_appends_random_suffix_on_slug_collision(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        existing = _make_section(slug="new-section")
        new_section = _make_section(title="New Section", slug="new-section-abc123")

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": existing}),
        ]
        db.execute.side_effect = execute_results

        async def _fake_refresh(obj):
            obj.id = new_section.id
            obj.title = "New Section"
            obj.slug = "new-section-abc123"
            obj.parent_id = None
            obj.description = None
            obj.sort_order = 0
            obj.created_at = new_section.created_at

        db.refresh.side_effect = _fake_refresh

        app = _build_app(user, db, redis)
        resp = await _post(app, "/kb/sections", json={"title": "New Section"})

        assert resp.status_code == 201
        assert "new-section" in resp.json()["slug"]


# ── PUT /kb/sections/{id} ─────────────────────────────────────────────────────


class TestUpdateSection:
    @pytest.mark.asyncio
    async def test_updates_section(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section = _make_section(title="Old Title", slug="old-title")

        db.execute.return_value.scalar_one_or_none.return_value = section

        async def _fake_refresh(obj):
            obj.title = "New Title"

        db.refresh.side_effect = _fake_refresh

        with (
            patch("app.api.kb.sections.require_section_permission", new_callable=AsyncMock),
            patch(
                "app.api.kb.sections.resolve_section_permission", AsyncMock(return_value="editor")
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/sections/{section.id}",
                json={"title": "New Title"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value.scalar_one_or_none.return_value = None

        app = _build_app(user, db, redis)
        resp = await _put(
            app,
            f"/kb/sections/{uuid.uuid4()}",
            json={"title": "X"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_when_self_parent(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section = _make_section()

        db.execute.return_value.scalar_one_or_none.return_value = section

        with patch("app.api.kb.sections.require_section_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/sections/{section.id}",
                json={"parent_id": str(section.id)},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_404_when_parent_not_found_in_update(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section = _make_section()
        parent_id = uuid.uuid4()

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            MagicMock(**{"scalar_one_or_none.return_value": None}),
        ]
        db.execute.side_effect = execute_results

        with patch("app.api.kb.sections.require_section_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/sections/{section.id}",
                json={"parent_id": str(parent_id)},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_on_cycle_detection(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section = _make_section()
        parent_id = uuid.uuid4()
        parent_section = _make_section(id=parent_id)

        cycle_result = MagicMock()
        cycle_result.fetchone.return_value = (1,)

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            MagicMock(**{"scalar_one_or_none.return_value": parent_section}),
            cycle_result,
        ]
        db.execute.side_effect = execute_results

        with patch("app.api.kb.sections.require_section_permission", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/kb/sections/{section.id}",
                json={"parent_id": str(parent_id)},
            )

        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"].lower()


# ── DELETE /kb/sections/{id} ──────────────────────────────────────────────────


class TestDeleteSection:
    @pytest.mark.asyncio
    async def test_deletes_section_204(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        redis.lpush = AsyncMock()

        section = _make_section()

        child_result = MagicMock(**{"scalar_one_or_none.return_value": None})
        article_result = MagicMock(**{"scalar_one_or_none.return_value": None})

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            child_result,
            article_result,
            MagicMock(),
        ]
        db.execute.side_effect = execute_results

        with patch("app.api.kb.sections.push_audit_event", new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/kb/sections/{section.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deletes_section_by_local_manager_204(self):
        user = _make_user(role="user")
        db = _make_db()
        redis = _make_redis()
        redis.lpush = AsyncMock()

        section = _make_section()

        child_result = MagicMock(**{"scalar_one_or_none.return_value": None})
        article_result = MagicMock(**{"scalar_one_or_none.return_value": None})

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            child_result,
            article_result,
            MagicMock(),
        ]
        db.execute.side_effect = execute_results

        with (
            patch("app.api.kb.sections.push_audit_event", new_callable=AsyncMock),
            patch(
                "app.services.kb_acl.resolve.resolve_section_permission",
                AsyncMock(return_value="manager"),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/kb/sections/{section.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_returns_403_when_insufficient_permissions(self):
        user = _make_user(role="user")
        db = _make_db()
        redis = _make_redis()

        section = _make_section()

        db.execute.return_value.scalar_one_or_none.return_value = section

        with patch(
            "app.services.kb_acl.resolve.resolve_section_permission",
            AsyncMock(return_value="editor"),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/kb/sections/{section.id}")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_404_when_section_not_found(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value.scalar_one_or_none.return_value = None

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/kb/sections/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_409_when_has_children(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        section = _make_section()
        child = _make_section(parent_id=section.id)

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            MagicMock(**{"scalar_one_or_none.return_value": child}),
        ]
        db.execute.side_effect = execute_results

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/kb/sections/{section.id}")

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_409_when_has_active_articles(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        section = _make_section()
        article = MagicMock()

        execute_results = [
            MagicMock(**{"scalar_one_or_none.return_value": section}),
            MagicMock(**{"scalar_one_or_none.return_value": None}),
            MagicMock(**{"scalar_one_or_none.return_value": article}),
        ]
        db.execute.side_effect = execute_results

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/kb/sections/{section.id}")

        assert resp.status_code == 409
