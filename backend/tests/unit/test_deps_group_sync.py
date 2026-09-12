"""Покрытие _sync_keycloak_groups (app/api/deps.py).

Гарантирует, что членство в группах Keycloak пересинхронизируется из живого
access-token claim на каждом запросе (а не только при полном логине), и что при
реальном изменении групп сбрасываются per-user ACL-кэши.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import _sync_keycloak_groups


def make_user(groups: list[str] | None = None):
    return SimpleNamespace(id=uuid.uuid4(), keycloak_groups=groups or [])


def make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def patch_invalidators():
    return (
        patch("app.services.files_acl.invalidate_user_cache", new=AsyncMock()),
        patch("app.services.files_acl.invalidate_file_share_user_cache", new=AsyncMock()),
        patch("app.services.kb_acl.invalidate_user_cache", new=AsyncMock()),
        patch("app.services.photos_acl.invalidate_user_cache", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_groups_changed_persists_and_invalidates():
    user = make_user(groups=["/old"])
    db = make_db()
    redis = MagicMock()
    claims = {"groups": ["/old", "/dept-x"]}

    p_files, p_share, p_kb, p_photos = patch_invalidators()
    with p_files as m_files, p_share as m_share, p_kb as m_kb, p_photos as m_photos:
        await _sync_keycloak_groups(db, redis, user, claims)

    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert set(user.keycloak_groups) == {"/old", "/dept-x"}
    m_files.assert_awaited_once_with(redis, user.id)
    m_share.assert_awaited_once_with(redis, user.id)
    m_kb.assert_awaited_once_with(redis, user.id)
    m_photos.assert_awaited_once_with(redis, user.id)


@pytest.mark.asyncio
async def test_groups_unchanged_is_noop_even_if_reordered():
    user = make_user(groups=["/a", "/b"])
    db = make_db()
    redis = MagicMock()
    claims = {"groups": ["/b", "/a"]}

    p_files, p_share, p_kb, p_photos = patch_invalidators()
    with p_files as m_files, p_share, p_kb, p_photos:
        await _sync_keycloak_groups(db, redis, user, claims)

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    m_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_groups_claim_is_noop():
    user = make_user(groups=["/keep"])
    db = make_db()
    redis = MagicMock()

    await _sync_keycloak_groups(db, redis, user, {})

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert user.keycloak_groups == ["/keep"]


@pytest.mark.asyncio
async def test_db_failure_rolls_back_and_keeps_old_groups():
    user = make_user(groups=["/old"])
    db = make_db()
    db.execute.side_effect = RuntimeError("db down")
    redis = MagicMock()
    claims = {"groups": ["/old", "/new"]}

    p_files, p_share, p_kb, p_photos = patch_invalidators()
    with p_files as m_files, p_share, p_kb, p_photos:
        await _sync_keycloak_groups(db, redis, user, claims)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    assert user.keycloak_groups == ["/old"]
    m_files.assert_not_awaited()
