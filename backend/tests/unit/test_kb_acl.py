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
from unittest.mock import AsyncMock, MagicMock

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
        from app.services.acl_base import SYSTEM_ALL_USERS_SUBJECT_ID

        user = SimpleNamespace(id=uuid.uuid4(), role="reader", keycloak_id=None, keycloak_groups=[])
        ids = await _subject_ids_for_user(user)
        assert str(user.id) in ids
        assert SYSTEM_ALL_USERS_SUBJECT_ID in ids
        assert len(ids) == 2

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
    import fnmatch
    keys = [k for batch in batches for k in batch]

    def _scan_iter(match=None, count=None):
        async def _gen():
            for k in keys:
                if match is None or fnmatch.fnmatch(k, match):
                    yield k

        return _gen()

    return _scan_iter


class TestInvalidateCaches:
    @pytest.mark.asyncio
    async def test_invalidate_section_deletes_keys(self):
        redis = AsyncMock()
        sec_id = uuid.uuid4()
        redis.scan_iter = _scan_iter_factory([f"kb_acl:u1:section:{sec_id}"])
        redis.delete = AsyncMock()
        await invalidate_section_cache(redis, sec_id)
        redis.delete.assert_called_once_with(f"kb_acl:u1:section:{sec_id}")

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
        art_id = uuid.uuid4()
        redis.scan_iter = _scan_iter_factory([f"kb_acl:u1:article:{art_id}"])
        redis.delete = AsyncMock()
        await invalidate_article_cache(redis, art_id)
        redis.delete.assert_called_once_with(f"kb_acl:u1:article:{art_id}")

    @pytest.mark.asyncio
    async def test_invalidate_redis_error_silenced(self):
        redis = AsyncMock()

        def _raising(match=None, count=None):
            raise Exception("redis down")

        redis.scan_iter = _raising
        await invalidate_section_cache(redis, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_invalidate_section_recursive_with_db(self):
        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory([
            "kb_acl:u1:section:sec1",
            "kb_acl:u1:section:sec2",
            "kb_acl:u1:article:art1",
        ])
        redis.delete = AsyncMock()

        db = AsyncMock()
        desc_res = MagicMock()
        desc_res.fetchall.return_value = [("sec1",), ("sec2",)]

        art_res = MagicMock()
        art_res.fetchall.return_value = [("art1",)]

        execute_calls = []
        async def execute_side_effect(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            if len(execute_calls) == 1:
                return desc_res
            else:
                return art_res

        db.execute = execute_side_effect

        await invalidate_section_cache(redis, uuid.uuid4(), db)

        deleted_keys = [call.args[0] for call in redis.delete.call_args_list]
        assert "kb_acl:u1:section:sec1" in deleted_keys
        assert "kb_acl:u1:section:sec2" in deleted_keys
        assert "kb_acl:u1:article:art1" in deleted_keys


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


# ── acl_base extra coverage ───────────────────────────────────────────────────


class TestSubjectIdsExtra:
    @pytest.mark.asyncio
    async def test_group_without_slash_adds_slash_variant(self):
        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader",
            keycloak_id=None, keycloak_groups=["devs"],
        )
        ids = await _subject_ids_for_user(user)
        assert "devs" in ids
        assert "/devs" in ids

    @pytest.mark.asyncio
    async def test_group_with_slash_adds_stripped_variant(self):
        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader",
            keycloak_id=None, keycloak_groups=["/engineering/backend"],
        )
        ids = await _subject_ids_for_user(user)
        assert "/engineering/backend" in ids
        assert "engineering/backend" in ids

    @pytest.mark.asyncio
    async def test_empty_string_group_skipped(self):
        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader",
            keycloak_id=None, keycloak_groups=["", "valid-group"],
        )
        ids = await _subject_ids_for_user(user)
        assert "" not in ids
        assert "valid-group" in ids

    @pytest.mark.asyncio
    async def test_non_list_groups_ignored(self):
        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader",
            keycloak_id=None, keycloak_groups="not-a-list",
        )
        ids = await _subject_ids_for_user(user)
        assert "not-a-list" not in ids


# ── batch_resolve_section_permissions ────────────────────────────────────────


class TestBatchResolveSectionPermissions:
    @pytest.mark.asyncio
    async def test_admin_returns_manager_for_all(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="admin")
        sections = [make_section() for _ in range(3)]
        db = make_db()
        redis = make_redis()
        result = await batch_resolve_section_permissions(user, sections, db, redis)
        assert all(v == "manager" for v in result.values())
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader")
        db = make_db()
        redis = make_redis()
        result = await batch_resolve_section_permissions(user, [], db, redis)
        assert result == {}

    @pytest.mark.asyncio
    async def test_created_by_shortcircuit(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader")
        section = make_section(created_by=user.id)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()
        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] == "manager"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=["viewer"])
        db = make_db()
        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] == "viewer"

    @pytest.mark.asyncio
    async def test_cache_hit_none_string(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=["none"])
        db = make_db()
        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] is None

    @pytest.mark.asyncio
    async def test_no_subject_ids_returns_none(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader", keycloak_id=None, keycloak_groups=[]
        )
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()
        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] is None

    @pytest.mark.asyncio
    async def test_db_query_resolves_permission(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [(str(section.id), "editor")]
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] == "editor"

    @pytest.mark.asyncio
    async def test_redis_mget_exception_falls_back(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(side_effect=Exception("redis down"))
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] is None


# ── batch_resolve_article_permissions ─────────────────────────────────────────


class TestBatchResolveArticlePermissions:
    @pytest.mark.asyncio
    async def test_admin_returns_manager_for_all(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="admin")
        articles = [make_article() for _ in range(3)]
        db = make_db()
        redis = make_redis()
        result = await batch_resolve_article_permissions(user, articles, db, redis)
        assert all(v == "manager" for v in result.values())

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="reader")
        db = make_db()
        redis = make_redis()
        result = await batch_resolve_article_permissions(user, [], db, redis)
        assert result == {}

    @pytest.mark.asyncio
    async def test_created_by_shortcircuit(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="reader")
        article = make_article(created_by=user.id)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()
        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] == "manager"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        article = make_article()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=["editor"])
        db = make_db()
        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] == "editor"

    @pytest.mark.asyncio
    async def test_no_subject_ids_all_none(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader", keycloak_id=None, keycloak_groups=[]
        )
        article = make_article()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()
        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] is None

    @pytest.mark.asyncio
    async def test_direct_articles_resolved(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        article = make_article(inherit_permissions=False)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [(article.id, "viewer")]
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] == "viewer"

    @pytest.mark.asyncio
    async def test_inherit_articles_delegated_to_sections(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(role="reader", keycloak_id="kc-1")
        sec_id = uuid.uuid4()
        article = make_article(inherit_permissions=True, section_id=sec_id)
        redis = AsyncMock()
        redis.mget = AsyncMock(side_effect=[
            [None],
            ["editor"],
        ])
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis.pipeline = MagicMock(return_value=pipe_mock)

        section = make_section()
        section.id = sec_id
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [section]
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert article.id in result


# ── apply_article_visibility ──────────────────────────────────────────────────


class TestApplyArticleVisibility:
    @pytest.mark.asyncio
    async def test_admin_returns_stmt_unchanged(self):
        from sqlalchemy import select

        from app.models.kb import KbArticle
        from app.services.kb_acl import apply_article_visibility

        user = make_user(role="admin")
        db = make_db()
        stmt = select(KbArticle)
        result = await apply_article_visibility(stmt, user, db)
        assert result is stmt

    @pytest.mark.asyncio
    async def test_no_subject_ids_adds_created_by_filter(self):
        from sqlalchemy import select

        from app.models.kb import KbArticle
        from app.services.kb_acl import apply_article_visibility

        user = SimpleNamespace(
            id=uuid.uuid4(), role="reader", keycloak_id=None, keycloak_groups=[]
        )
        db = make_db()
        stmt = select(KbArticle)
        result = await apply_article_visibility(stmt, user, db)
        compiled = str(result.compile())
        assert "created_by" in compiled

    @pytest.mark.asyncio
    async def test_with_subject_ids_adds_acl_filter(self):
        from sqlalchemy import select

        from app.models.kb import KbArticle
        from app.services.kb_acl import apply_article_visibility

        user = make_user(role="reader", keycloak_id="kc-1")
        db = make_db()
        stmt = select(KbArticle)
        result = await apply_article_visibility(stmt, user, db)
        compiled = str(result.compile())
        assert "kb_article_permissions" in compiled or "inherit_permissions" in compiled


class TestScanAndDelete:
    @pytest.mark.asyncio
    async def test_batches_when_many_keys(self):
        from app.services.acl_base import scan_and_delete

        deleted_calls = []
        keys_returned = [f"key:{i}" for i in range(3)]

        async def _mock_scan_iter(match, count):
            for k in keys_returned:
                yield k

        mock_redis = AsyncMock()
        mock_redis.scan_iter = _mock_scan_iter
        mock_redis.delete = AsyncMock()

        await scan_and_delete(mock_redis, "key:*", batch=2)
        assert mock_redis.delete.await_count >= 1


# ── Additional branch coverage ────────────────────────────────────────────────


class TestInvalidateSectionCacheWithDb:
    @pytest.mark.asyncio
    async def test_with_db_cascades_inherited_articles(self):
        from app.services.kb_acl import invalidate_section_cache

        art_id = uuid.uuid4()
        section_id = uuid.uuid4()

        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory([])
        redis.delete = AsyncMock()

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [(art_id,)]
        db.execute = AsyncMock(return_value=result_mock)

        await invalidate_section_cache(redis, section_id, db=db)
        db.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_with_db_no_inherited_articles(self):
        from app.services.kb_acl import invalidate_section_cache

        section_id = uuid.uuid4()
        redis = AsyncMock()
        redis.scan_iter = _scan_iter_factory([])
        redis.delete = AsyncMock()

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        await invalidate_section_cache(redis, section_id, db=db)
        db.execute.assert_awaited()


class TestResolveSectionEmptySubjectIds:
    @pytest.mark.asyncio
    async def test_empty_subject_ids_returns_none(self):
        from unittest.mock import patch as _patch

        from app.services.kb_acl import resolve_section_permission

        user = make_user()
        section = make_section()
        redis = make_redis()
        db = make_db()

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await resolve_section_permission(user, section, db, redis)
        assert result is None


class TestResolveArticleExtraBranches:
    @pytest.mark.asyncio
    async def test_inherit_false_empty_subject_ids(self):
        from unittest.mock import patch as _patch

        from app.services.kb_acl import resolve_article_permission

        user = make_user()
        article = make_article(inherit_permissions=False)
        redis = make_redis()
        db = make_db()

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await resolve_article_permission(user, article, db, redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_inherit_true_section_not_found_in_db(self):
        from app.services.kb_acl import resolve_article_permission

        user = make_user(keycloak_id="kc-1")
        section_id = uuid.uuid4()
        article = make_article(inherit_permissions=True, section_id=section_id)
        redis = make_redis()

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await resolve_article_permission(user, article, db, redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_inherit_true_no_section_id_empty_subject_ids(self):
        from unittest.mock import patch as _patch

        from app.services.kb_acl import resolve_article_permission

        user = make_user()
        article = make_article(inherit_permissions=True, section_id=None)
        redis = make_redis()
        db = make_db()

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await resolve_article_permission(user, article, db, redis)
        assert result is None


class TestBatchResolveSectionExtraBranches:
    def _make_pipe_mock(self, execute_raises=False):
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        if execute_raises:
            pipe_mock.execute = AsyncMock(side_effect=Exception("redis dead"))
        else:
            pipe_mock.execute = AsyncMock(return_value=[])
        return pipe_mock

    @pytest.mark.asyncio
    async def test_empty_subject_ids_pipeline_write(self):
        from unittest.mock import patch as _patch

        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user()
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock()
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] is None

    @pytest.mark.asyncio
    async def test_db_returns_unknown_root_id(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock()
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [(str(uuid.uuid4()), "editor")]
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert result[section.id] is None

    @pytest.mark.asyncio
    async def test_pipeline_exception_silenced(self):
        from app.services.kb_acl import batch_resolve_section_permissions

        user = make_user(keycloak_id="kc-1")
        section = make_section()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock(execute_raises=True)
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_section_permissions(user, [section], db, redis)
        assert section.id in result


class TestBatchResolveArticleExtraBranches:
    def _make_pipe_mock(self, execute_raises=False):
        pipe_mock = AsyncMock()
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        pipe_mock.setex = MagicMock()
        if execute_raises:
            pipe_mock.execute = AsyncMock(side_effect=Exception("redis dead"))
        else:
            pipe_mock.execute = AsyncMock(return_value=[])
        return pipe_mock

    @pytest.mark.asyncio
    async def test_empty_subject_ids_all_none_pipeline(self):
        from unittest.mock import patch as _patch

        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user()
        article = make_article()
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock()
        redis.pipeline = MagicMock(return_value=pipe_mock)
        db = make_db()

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] is None

    @pytest.mark.asyncio
    async def test_direct_articles_unknown_art_id_ignored(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(keycloak_id="kc-1")
        article = make_article(inherit_permissions=False, section_id=None)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock()
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [(str(uuid.uuid4()), "editor")]
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert result[article.id] is None

    @pytest.mark.asyncio
    async def test_pipeline_exception_silenced(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(keycloak_id="kc-1")
        article = make_article(inherit_permissions=False, section_id=None)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock(execute_raises=True)
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert article.id in result

    @pytest.mark.asyncio
    async def test_inherit_article_section_id_none_skipped(self):
        from app.services.kb_acl import batch_resolve_article_permissions

        user = make_user(keycloak_id="kc-1")
        article = make_article(inherit_permissions=True, section_id=None)
        redis = AsyncMock()
        redis.mget = AsyncMock(return_value=[None])
        pipe_mock = self._make_pipe_mock()
        redis.pipeline = MagicMock(return_value=pipe_mock)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await batch_resolve_article_permissions(user, [article], db, redis)
        assert article.id in result


class TestApplyArticleVisibilityExtraBranches:
    @pytest.mark.asyncio
    async def test_empty_subject_ids_adds_created_by_only(self):
        from unittest.mock import patch as _patch

        from sqlalchemy import select

        from app.models.kb import KbArticle
        from app.services.kb_acl import apply_article_visibility

        user = make_user()
        db = make_db()
        stmt = select(KbArticle)

        with _patch("app.services.kb_acl._subject_ids_for_user", AsyncMock(return_value=[])):
            result = await apply_article_visibility(stmt, user, db)
        compiled = str(result.compile())
        assert "created_by" in compiled
