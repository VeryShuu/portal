"""
Unit-тесты Phase 3.5 — ACL системы базы знаний.

Покрытие:
- _perm_gte: все комбинации уровней
- resolve_section_permission: admin override, создатель, кэш-хит, рекурсия
- resolve_article_permission: admin, создатель, inherit=False, inherit=True с разделом
- require_article_permission: достаточно прав → OK, недостаточно → 403
- require_section_permission: аналогично
- invalidate_section_cache / invalidate_article_cache
- _subject_ids_for_user: keycloak_id + группы
- filter_accessible_sections: только доступные
- filter_accessible_articles: только доступные
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kb_acl import (
    _perm_gte,
    _subject_ids_for_user,
    filter_accessible_articles,
    filter_accessible_sections,
    invalidate_article_cache,
    invalidate_section_cache,
    require_article_permission,
    require_section_permission,
    resolve_article_permission,
    resolve_section_permission,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_user(role: str = "reader", keycloak_id: str | None = None, groups: list | None = None):
    uid = uuid.uuid4()
    return SimpleNamespace(
        id=uid,
        role=role,
        keycloak_id=keycloak_id or str(uid),
        keycloak_groups=groups or [],
    )


def make_section(created_by=None, parent_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        parent_id=parent_id,
        created_by=created_by,
    )


def make_article(created_by=None, section_id=None, inherit_permissions: bool = True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        created_by=created_by,
        section_id=section_id,
        inherit_permissions=inherit_permissions,
    )


def make_redis(cached: str | None = None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=cached)
    r.setex = AsyncMock()
    r.keys = AsyncMock(return_value=[])
    r.delete = AsyncMock()
    return r


def make_db(perm_rows: list[str] | None = None, section: object | None = None):
    db = AsyncMock()
    result_mock = MagicMock()
    rows = [(p,) for p in (perm_rows or [])]
    result_mock.fetchall.return_value = rows
    result_mock.fetchone.return_value = rows[0] if rows else None
    result_mock.scalar_one_or_none.return_value = section

    async def execute_side_effect(stmt, *args, **kwargs):
        return result_mock

    db.execute = execute_side_effect
    return db


# ── _perm_gte ─────────────────────────────────────────────────────────────────


class TestPermGte:
    def test_manager_gte_viewer(self):
        assert _perm_gte("manager", "viewer") is True

    def test_manager_gte_editor(self):
        assert _perm_gte("manager", "editor") is True

    def test_manager_gte_manager(self):
        assert _perm_gte("manager", "manager") is True

    def test_editor_gte_viewer(self):
        assert _perm_gte("editor", "viewer") is True

    def test_editor_gte_editor(self):
        assert _perm_gte("editor", "editor") is True

    def test_editor_not_gte_manager(self):
        assert _perm_gte("editor", "manager") is False

    def test_viewer_gte_viewer(self):
        assert _perm_gte("viewer", "viewer") is True

    def test_viewer_not_gte_editor(self):
        assert _perm_gte("viewer", "editor") is False

    def test_none_not_gte_viewer(self):
        assert _perm_gte(None, "viewer") is False

    def test_unknown_not_gte_viewer(self):
        assert _perm_gte("unknown", "viewer") is False


# ── _subject_ids_for_user ─────────────────────────────────────────────────────


class TestSubjectIds:
    @pytest.mark.asyncio
    async def test_keycloak_id_included(self):
        user = make_user(keycloak_id="kc-123")
        ids = await _subject_ids_for_user(user)
        assert "kc-123" in ids

    @pytest.mark.asyncio
    async def test_groups_included(self):
        user = make_user(keycloak_id="kc-abc", groups=["group-1", "group-2"])
        ids = await _subject_ids_for_user(user)
        assert "kc-abc" in ids
        assert "group-1" in ids
        assert "group-2" in ids

    @pytest.mark.asyncio
    async def test_no_keycloak_id(self):
        user = SimpleNamespace(id=uuid.uuid4(), role="reader", keycloak_id=None, keycloak_groups=[])
        ids = await _subject_ids_for_user(user)
        assert str(user.id) in ids
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_no_groups_attr(self):
        user = SimpleNamespace(id=uuid.uuid4(), role="reader", keycloak_id="kc-1")
        ids = await _subject_ids_for_user(user)
        assert "kc-1" in ids


# ── resolve_section_permission ────────────────────────────────────────────────


class TestResolveSectionPermission:
    @pytest.mark.asyncio
    async def test_admin_always_manager(self):
        user = make_user(role="admin")
        section = make_section()
        db = make_db()
        redis = make_redis()
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm == "manager"

    @pytest.mark.asyncio
    async def test_creator_gets_manager(self):
        user = make_user(role="reader")
        section = make_section(created_by=user.id)
        db = make_db()
        redis = make_redis()
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm == "manager"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        user = make_user(role="reader")
        section = make_section()
        db = make_db()
        redis = make_redis(cached="editor")
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm == "editor"
        db.execute  # should not be called beyond cache
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_none(self):
        user = make_user(role="reader")
        section = make_section()
        db = make_db()
        redis = make_redis(cached="none")
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm is None

    @pytest.mark.asyncio
    async def test_direct_permission_found(self):
        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        db = make_db(perm_rows=["viewer"])
        redis = make_redis()
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm == "viewer"

    @pytest.mark.asyncio
    async def test_no_permission_returns_none(self):
        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        db = make_db(perm_rows=[], section=None)
        redis = make_redis()
        perm = await resolve_section_permission(user, section, db, redis)
        assert perm is None

    @pytest.mark.asyncio
    async def test_result_cached(self):
        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        db = make_db(perm_rows=["editor"])
        redis = make_redis()
        await resolve_section_permission(user, section, db, redis)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[2] == "editor"


# ── resolve_article_permission ────────────────────────────────────────────────


class TestResolveArticlePermission:
    @pytest.mark.asyncio
    async def test_admin_always_manager(self):
        user = make_user(role="admin")
        article = make_article()
        db = make_db()
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "manager"

    @pytest.mark.asyncio
    async def test_creator_gets_manager(self):
        user = make_user(role="reader")
        article = make_article(created_by=user.id)
        db = make_db()
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "manager"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        user = make_user(role="reader")
        article = make_article()
        db = make_db()
        redis = make_redis(cached="viewer")
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "viewer"

    @pytest.mark.asyncio
    async def test_inherit_false_checks_article_perms(self):
        user = make_user(role="reader", keycloak_id="kc-u1")
        article = make_article(inherit_permissions=False)
        db = make_db(perm_rows=["editor"])
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "editor"

    @pytest.mark.asyncio
    async def test_inherit_false_no_perm(self):
        user = make_user(role="reader", keycloak_id="kc-u1")
        article = make_article(inherit_permissions=False)
        db = make_db(perm_rows=[])
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm is None

    @pytest.mark.asyncio
    async def test_inherit_true_no_section_uses_article_perms(self):
        user = make_user(role="reader", keycloak_id="kc-u1")
        article = make_article(inherit_permissions=True, section_id=None)
        db = make_db(perm_rows=["viewer"])
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "viewer"

    @pytest.mark.asyncio
    async def test_inherit_true_with_section(self):
        user = make_user(role="reader", keycloak_id="kc-u1")
        sec_id = uuid.uuid4()
        article = make_article(inherit_permissions=True, section_id=sec_id)
        parent_section = make_section()
        db = AsyncMock()

        call_count = [0]

        async def execute_side(stmt, *args, **kwargs):
            r = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # GET section
                r.scalar_one_or_none.return_value = parent_section
                r.fetchall.return_value = []
                r.fetchone.return_value = None
            else:
                # section permissions query
                r.fetchall.return_value = [("manager",)]
                r.fetchone.return_value = ("manager",)
                r.scalar_one_or_none.return_value = None
            return r

        db.execute = execute_side
        redis = make_redis()
        perm = await resolve_article_permission(user, article, db, redis)
        assert perm == "manager"


# ── require_article_permission ────────────────────────────────────────────────


class TestRequireArticlePermission:
    @pytest.mark.asyncio
    async def test_sufficient_permission_ok(self):
        user = make_user(role="admin")
        article = make_article()
        db = make_db()
        redis = make_redis()
        await require_article_permission(user, article, "manager", db, redis)

    @pytest.mark.asyncio
    async def test_insufficient_raises_403(self):
        from fastapi import HTTPException

        user = make_user(role="reader", keycloak_id="kc-1")
        article = make_article()
        db = make_db(perm_rows=[])
        redis = make_redis()
        with pytest.raises(HTTPException) as exc:
            await require_article_permission(user, article, "viewer", db, redis)
        assert exc.value.status_code == 403


# ── require_section_permission ────────────────────────────────────────────────


class TestRequireSectionPermission:
    @pytest.mark.asyncio
    async def test_admin_ok(self):
        user = make_user(role="admin")
        section = make_section()
        db = make_db()
        redis = make_redis()
        await require_section_permission(user, section, "manager", db, redis)

    @pytest.mark.asyncio
    async def test_no_access_raises_403(self):
        from fastapi import HTTPException

        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        db = make_db(perm_rows=[], section=None)
        redis = make_redis()
        with pytest.raises(HTTPException) as exc:
            await require_section_permission(user, section, "viewer", db, redis)
        assert exc.value.status_code == 403


# ── invalidate caches ─────────────────────────────────────────────────────────


def _scan_iter_factory(*batches):
    """Build an async iterator that yields keys for redis.scan_iter mock."""
    keys = [k for batch in batches for k in batch]

    def _scan_iter(match=None, count=None):
        async def _gen():
            for k in keys:
                yield k

        return _gen()

    return _scan_iter


class TestInvalidateCaches:
    @pytest.mark.asyncio
    async def test_invalidate_section_deletes_keys(self):
        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory(["kb_acl:u1:section:s1"])
        redis.delete = AsyncMock()
        sec_id = uuid.uuid4()
        await invalidate_section_cache(redis, sec_id)
        redis.delete.assert_called_once_with("kb_acl:u1:section:s1")

    @pytest.mark.asyncio
    async def test_invalidate_section_no_keys(self):
        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory([])
        redis.delete = AsyncMock()
        await invalidate_section_cache(redis, uuid.uuid4())
        redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_article_deletes_keys(self):
        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory(["kb_acl:u1:article:a1"])
        redis.delete = AsyncMock()
        await invalidate_article_cache(redis, uuid.uuid4())
        redis.delete.assert_called_once_with("kb_acl:u1:article:a1")

    @pytest.mark.asyncio
    async def test_invalidate_redis_error_silenced(self):
        redis = AsyncMock()

        def _raising(match=None, count=None):
            raise Exception("redis down")

        redis.scan_iter = _raising
        await invalidate_section_cache(redis, uuid.uuid4())


# ── filter_accessible_* ───────────────────────────────────────────────────────


class TestFilterAccessible:
    @pytest.mark.asyncio
    async def test_admin_sees_all_sections(self):
        user = make_user(role="admin")
        sections = [make_section() for _ in range(5)]
        db = make_db()
        redis = make_redis()
        result = await filter_accessible_sections(user, sections, db, redis)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_reader_sees_only_own_sections(self):
        user = make_user(role="reader")
        own_section = make_section(created_by=user.id)
        other_section = make_section()
        db = make_db(perm_rows=[])
        redis = make_redis()
        result = await filter_accessible_sections(user, [own_section, other_section], db, redis)
        assert own_section in result
        assert other_section not in result

    @pytest.mark.asyncio
    async def test_admin_sees_all_articles(self):
        user = make_user(role="admin")
        articles = [make_article() for _ in range(3)]
        db = make_db()
        redis = make_redis()
        result = await filter_accessible_articles(user, articles, db, redis)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_reader_sees_only_accessible_articles(self):
        user = make_user(role="reader")
        own_article = make_article(created_by=user.id)
        other_article = make_article(inherit_permissions=False)
        db = make_db(perm_rows=[])
        redis = make_redis()
        result = await filter_accessible_articles(user, [own_article, other_article], db, redis)
        assert own_article in result
        assert other_article not in result
