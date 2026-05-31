"""Unit-тесты подзадачи «Создатель» в правах папок (sharing.md §9).

Покрытие:
- _merge_creator: создатель добавляется первым; дедуп с существующей user-записью;
  None-creator → список без изменений
- _is_creator_subject: user==created_by → True; группа/чужой user → False
- _build_creator_entry: формирует PermissionPublic(is_creator=True, permission=manager)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.files.permissions import (
    _build_creator_entry,
    _is_creator_subject,
    _merge_creator,
)
from app.schemas.files import PermissionPublic


def _entry(subject_id: str, subject_type: str = "user", is_creator: bool = False):
    return PermissionPublic(
        id=None if is_creator else uuid.uuid4(),
        folder_id=uuid.uuid4(),
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name="Name",
        permission="manager" if is_creator else "viewer",
        is_creator=is_creator,
    )


# ── _merge_creator ───────────────────────────────────────────────────────────────


def test_merge_creator_none_returns_entries_unchanged():
    entries = [_entry("u1")]
    assert _merge_creator(entries, None) == entries


def test_merge_creator_prepends_first():
    creator = _entry("creator", is_creator=True)
    entries = [_entry("u1"), _entry("u2")]
    result = _merge_creator(entries, creator)
    assert result[0] is creator
    assert len(result) == 3


def test_merge_creator_dedups_existing_user_entry():
    creator = _entry("creator", is_creator=True)
    entries = [_entry("creator"), _entry("u2")]
    result = _merge_creator(entries, creator)
    assert result[0] is creator
    assert len(result) == 2
    assert all(not (e.subject_id == "creator" and not e.is_creator) for e in result)


def test_merge_creator_keeps_group_with_same_id():
    creator = _entry("shared-id", is_creator=True)
    entries = [_entry("shared-id", subject_type="group")]
    result = _merge_creator(entries, creator)
    # group with same id is NOT deduped (only user-type matches creator)
    assert len(result) == 2


# ── _is_creator_subject ──────────────────────────────────────────────────────────


def test_is_creator_subject_true():
    cid = uuid.uuid4()
    folder = SimpleNamespace(created_by=cid)
    assert _is_creator_subject(folder, "user", str(cid)) is True


def test_is_creator_subject_group_false():
    cid = uuid.uuid4()
    folder = SimpleNamespace(created_by=cid)
    assert _is_creator_subject(folder, "group", str(cid)) is False


def test_is_creator_subject_other_user_false():
    folder = SimpleNamespace(created_by=uuid.uuid4())
    assert _is_creator_subject(folder, "user", str(uuid.uuid4())) is False


def test_is_creator_subject_no_creator_false():
    folder = SimpleNamespace(created_by=None)
    assert _is_creator_subject(folder, "user", str(uuid.uuid4())) is False


# ── _build_creator_entry ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_creator_entry_none_when_no_created_by():
    folder = SimpleNamespace(id=uuid.uuid4(), created_by=None, nc_path="x")
    db = MagicMock()
    assert await _build_creator_entry(db, folder) is None


@pytest.mark.asyncio
async def test_build_creator_entry_none_when_user_missing():
    folder = SimpleNamespace(id=uuid.uuid4(), created_by=uuid.uuid4(), nc_path="x")
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    assert await _build_creator_entry(db, folder) is None


@pytest.mark.asyncio
async def test_build_creator_entry_builds_manager_is_creator():
    cid = uuid.uuid4()
    folder = SimpleNamespace(id=uuid.uuid4(), created_by=cid, nc_path="x")
    creator = SimpleNamespace(id=cid, full_name="Ivan Petrov", email="ivan@example.com")
    res = MagicMock()
    res.scalar_one_or_none.return_value = creator
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)

    entry = await _build_creator_entry(db, folder)
    assert entry is not None
    assert entry.is_creator is True
    assert entry.permission == "manager"
    assert entry.id is None
    assert entry.subject_id == str(cid)
    assert entry.email == "ivan@example.com"
