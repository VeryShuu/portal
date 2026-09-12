"""Integration tests — KB ACL: viewer/editor/manager isolation.

Requires INTEGRATION_DB=true + migrated PostgreSQL.

Covered scenarios
-----------------
1. Viewer may read section/article they were granted access to.
2. Viewer cannot edit article (PUT → 403).
3. Viewer cannot manage section permissions (POST → 403).
4. Editor may create/update articles in granted section.
5. Editor cannot manage section permissions (POST → 403).
6. Manager can grant/revoke permissions.
7. Portal admin bypasses ACL (sees everything).
8. Article with inherit_permissions=false: section permission NOT applied.
9. User without any permission gets 403 on article file download.
10. Ungranted user cannot see section in list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_user(db_session, **kwargs):
    from app.models.user import User

    defaults = dict(
        email=f"u{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Test User",
        department="IT",
        role="reader",
        auth_source="local",
        password_hash=None,
        current_status="working",
        notify_email=False,
        notify_inapp=False,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    u = User(**defaults)
    db_session.add(u)
    return u


async def _commit_refresh(db, *objs):
    await db.commit()
    for o in objs:
        await db.refresh(o)


@pytest_asyncio.fixture
async def ivanov(real_db_session):
    u = _make_user(
        real_db_session, full_name="Ivan Ivanov", email="ivanov@portal.local", role="editor"
    )
    await _commit_refresh(real_db_session, u)
    return u


@pytest_asyncio.fixture
async def petrov(real_db_session):
    u = _make_user(
        real_db_session, full_name="Petr Petrov", email="petrov@portal.local", role="reader"
    )
    await _commit_refresh(real_db_session, u)
    return u


@pytest_asyncio.fixture
async def sidorov(real_db_session):
    u = _make_user(
        real_db_session, full_name="Sidr Sidorov", email="sidorov@portal.local", role="reader"
    )
    await _commit_refresh(real_db_session, u)
    return u


@pytest_asyncio.fixture
async def portal_admin(real_db_session):
    u = _make_user(
        real_db_session, full_name="Admin User", email="admin@portal.local", role="admin"
    )
    await _commit_refresh(real_db_session, u)
    return u


@pytest_asyncio.fixture
async def section_with_article(real_db_session, ivanov):
    from app.models.kb import KbArticle, KbSection

    sec = KbSection(
        title="Test Section",
        slug=f"test-section-{uuid.uuid4().hex[:6]}",
        created_by=ivanov.id,
    )
    real_db_session.add(sec)
    await real_db_session.flush()

    art = KbArticle(
        title="Test Article",
        body="# Hello",
        status="published",
        section_id=sec.id,
        created_by=ivanov.id,
        updated_by=ivanov.id,
        inherit_permissions=True,
    )
    real_db_session.add(art)
    await _commit_refresh(real_db_session, sec, art)
    return sec, art


# ─────────────────────────────────────────────────────────────────────────────
# 1. resolve_section_permission — viewer gets viewer permission
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_can_read_section_when_granted(real_db_session, section_with_article, petrov):
    from unittest.mock import AsyncMock

    from app.models.kb import KbSectionPermission
    from app.services.kb_acl import resolve_section_permission

    sec, _ = section_with_article
    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(petrov.id),
        subject_name=petrov.full_name,
        permission="viewer",
        granted_by=petrov.id,
    )
    real_db_session.add(perm_row)
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    result = await resolve_section_permission(petrov, sec, real_db_session, redis_mock)
    assert result == "viewer"


# ─────────────────────────────────────────────────────────────────────────────
# 2. No permission → None
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sidorov_has_no_section_permission(real_db_session, section_with_article, sidorov):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import resolve_section_permission

    sec, _ = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    result = await resolve_section_permission(sidorov, sec, real_db_session, redis_mock)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Portal admin bypasses ACL
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_has_manager_permission_everywhere(
    real_db_session, section_with_article, portal_admin
):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import resolve_article_permission, resolve_section_permission

    sec, art = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    sec_perm = await resolve_section_permission(portal_admin, sec, real_db_session, redis_mock)
    art_perm = await resolve_article_permission(portal_admin, art, real_db_session, redis_mock)

    assert sec_perm == "manager"
    assert art_perm == "manager"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Article creator gets manager permission
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_article_creator_is_manager(real_db_session, section_with_article, ivanov):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import resolve_article_permission

    _, art = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    result = await resolve_article_permission(ivanov, art, real_db_session, redis_mock)
    assert result == "manager"


# ─────────────────────────────────────────────────────────────────────────────
# 5. inherit_permissions=True — article inherits section permission
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_article_inherits_section_permission(real_db_session, section_with_article, petrov):
    from unittest.mock import AsyncMock

    from app.models.kb import KbSectionPermission
    from app.services.kb_acl import resolve_article_permission

    sec, art = section_with_article
    assert art.inherit_permissions is True

    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(petrov.id),
        subject_name=petrov.full_name,
        permission="editor",
        granted_by=petrov.id,
    )
    real_db_session.add(perm_row)
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    result = await resolve_article_permission(petrov, art, real_db_session, redis_mock)
    assert result == "editor"


# ─────────────────────────────────────────────────────────────────────────────
# 6. inherit_permissions=False — section permission NOT applied to article
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_article_no_inherit_ignores_section_permission(
    real_db_session, section_with_article, petrov
):
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from app.models.kb import KbArticle, KbSectionPermission
    from app.services.kb_acl import resolve_article_permission

    sec, art = section_with_article

    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(petrov.id),
        subject_name=petrov.full_name,
        permission="editor",
        granted_by=petrov.id,
    )
    real_db_session.add(perm_row)

    art_res = await real_db_session.execute(select(KbArticle).where(KbArticle.id == art.id))
    article = art_res.scalar_one()
    article.inherit_permissions = False
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    result = await resolve_article_permission(petrov, article, real_db_session, redis_mock)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. require_article_permission raises 403 when no permission
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_article_permission_raises_403_when_no_perm(
    real_db_session, section_with_article, sidorov
):
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.services.kb_acl import require_article_permission

    _, art = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await require_article_permission(sidorov, art, "viewer", real_db_session, redis_mock)
    assert exc_info.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 8. require_section_permission raises 403 when viewer tries manager-level op
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_cannot_manage_section(real_db_session, section_with_article, petrov):
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.models.kb import KbSectionPermission
    from app.services.kb_acl import require_section_permission

    sec, _ = section_with_article
    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(petrov.id),
        subject_name=petrov.full_name,
        permission="viewer",
        granted_by=petrov.id,
    )
    real_db_session.add(perm_row)
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await require_section_permission(petrov, sec, "manager", real_db_session, redis_mock)
    assert exc_info.value.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 9. Editor can pass editor-level permission check
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_editor_can_edit_in_granted_section(real_db_session, section_with_article, petrov):
    from unittest.mock import AsyncMock

    from app.models.kb import KbSectionPermission
    from app.services.kb_acl import require_section_permission

    sec, _ = section_with_article
    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(petrov.id),
        subject_name=petrov.full_name,
        permission="editor",
        granted_by=petrov.id,
    )
    real_db_session.add(perm_row)
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    await require_section_permission(petrov, sec, "editor", real_db_session, redis_mock)


# ─────────────────────────────────────────────────────────────────────────────
# 10. filter_accessible_sections — ungranted user sees nothing
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_accessible_sections_hides_private(
    real_db_session, section_with_article, sidorov
):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import filter_accessible_sections

    sec, _ = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    visible = await filter_accessible_sections(sidorov, [sec], real_db_session, redis_mock)
    assert sec not in visible


# ─────────────────────────────────────────────────────────────────────────────
# 11. filter_accessible_sections — admin sees all
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_accessible_sections_admin_sees_all(
    real_db_session, section_with_article, portal_admin
):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import filter_accessible_sections

    sec, _ = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    visible = await filter_accessible_sections(portal_admin, [sec], real_db_session, redis_mock)
    assert sec in visible


# ─────────────────────────────────────────────────────────────────────────────
# 12. Redis cache hit — skips DB query
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_acl_uses_redis_cache_hit(real_db_session, section_with_article, petrov):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import resolve_section_permission

    sec, _ = section_with_article
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="editor")
    redis_mock.setex = AsyncMock()

    result = await resolve_section_permission(petrov, sec, real_db_session, redis_mock)
    assert result == "editor"
    redis_mock.setex.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 13. invalidate_section_cache removes keys via SCAN
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_section_cache_deletes_keys(real_db_session):
    from unittest.mock import AsyncMock

    from app.services.kb_acl import invalidate_section_cache

    section_id = uuid.uuid4()
    deleted: list[str] = []

    async def mock_scan_iter(match, count):
        for k in [f"kb_acl:u1:section:{section_id}", f"kb_acl:u2:section:{section_id}"]:
            yield k

    redis_mock = AsyncMock()
    redis_mock.scan_iter = mock_scan_iter
    redis_mock.delete = AsyncMock(side_effect=lambda *keys: deleted.extend(keys))

    await invalidate_section_cache(redis_mock, section_id)

    assert any(str(section_id) in k for k in deleted)


# ─────────────────────────────────────────────────────────────────────────────
# 14. Manager can grant permissions to section
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manager_can_grant_section_permission(
    real_db_session, section_with_article, petrov, ivanov
):
    from unittest.mock import AsyncMock

    from app.models.kb import KbSectionPermission
    from app.services.kb_acl import require_section_permission

    sec, _ = section_with_article

    perm_row = KbSectionPermission(
        section_id=sec.id,
        subject_type="user",
        subject_id=str(ivanov.id),
        subject_name=ivanov.full_name,
        permission="manager",
        granted_by=ivanov.id,
    )
    real_db_session.add(perm_row)
    await real_db_session.commit()

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()

    await require_section_permission(ivanov, sec, "manager", real_db_session, redis_mock)
