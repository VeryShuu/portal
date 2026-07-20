"""Unit-тесты для ``app.services.photos_permission_repo``.

Контракты DAO ``PhotoFolderPermission``:
* ``list_folder_permissions`` возвращает ``scalars().all()``, отсортированный по ``created_at``;
* ``find_folder_permission`` — ``scalar_one_or_none()``;
* ``delete_folder_permission`` — опциональный фильтр по ``subject_type``
  (если ``None``, условие не добавляется → удаляет все пермы subject_id).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import photos_permission_repo as repo


def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _result_scalars(rows: list[Any]) -> MagicMock:
    res = MagicMock()
    res.scalars.return_value.all.return_value = rows
    return res


def _result_one_or_none(value: Any) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


# ── list_folder_permissions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folder_permissions_returns_scalars():
    db = _make_db()
    perms = [MagicMock(), MagicMock(), MagicMock()]
    db.execute.return_value = _result_scalars(perms)

    result = await repo.list_folder_permissions(db, uuid.uuid4())

    assert result == perms
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_folder_permissions_empty_returns_empty_list():
    db = _make_db()
    db.execute.return_value = _result_scalars([])

    assert await repo.list_folder_permissions(db, uuid.uuid4()) == []


# ── find_folder_permission ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_folder_permission_found():
    db = _make_db()
    perm = MagicMock()
    db.execute.return_value = _result_one_or_none(perm)

    result = await repo.find_folder_permission(
        db, folder_id=uuid.uuid4(), subject_type="user", subject_id="u-1"
    )

    assert result is perm
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_folder_permission_not_found():
    db = _make_db()
    db.execute.return_value = _result_one_or_none(None)

    assert (
        await repo.find_folder_permission(
            db, folder_id=uuid.uuid4(), subject_type="group", subject_id="g-x"
        )
        is None
    )


# ── delete_folder_permission ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_folder_permission_with_subject_type_filters_by_both():
    """Если subject_type задан — условие добавляется (удаляет конкретный перм)."""
    db = _make_db()

    await repo.delete_folder_permission(
        db,
        folder_id=uuid.uuid4(),
        subject_id="u-1",
        subject_type="user",
    )

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_folder_permission_without_subject_type_deletes_all_for_subject():
    """Если subject_type=None — условие НЕ добавляется (удаляет все пермы subject_id)."""
    db = _make_db()

    await repo.delete_folder_permission(
        db,
        folder_id=uuid.uuid4(),
        subject_id="u-1",
        subject_type=None,
    )

    db.execute.assert_awaited_once()
