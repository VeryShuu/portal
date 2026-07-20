"""Unit-тесты для ``app.services.photos_share_repo``.

Чистый DAO поверх ``PhotoShareToken`` / ``PhotoFolderShareToken``. Контракты:
* ``list_*`` возвращают ``Sequence`` из ``scalars().all()`` (для single-entity)
  или ``.all()`` (для join с folder-name);
* ``get_*`` / ``fetch_*`` / ``scalar_*`` возвращают single-or-None.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import photos_share_repo as repo


def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


def _result_scalars(rows: list[Any]) -> MagicMock:
    res = MagicMock()
    res.scalars.return_value.all.return_value = rows
    return res


def _result_rows(rows: list[Any]) -> MagicMock:
    res = MagicMock()
    res.all.return_value = rows
    return res


# ── list_folder_share_tokens ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folder_share_tokens_returns_scalars():
    db = _make_db()
    tokens = [MagicMock(), MagicMock()]
    db.execute.return_value = _result_scalars(tokens)

    result = await repo.list_folder_share_tokens(db, uuid.uuid4())

    assert result == tokens
    db.execute.assert_awaited_once()


# ── list_my_photo_shares ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_my_photo_shares_returns_scalars():
    db = _make_db()
    tokens = [MagicMock()]
    db.execute.return_value = _result_scalars(tokens)

    result = await repo.list_my_photo_shares(db, uuid.uuid4())

    assert result == tokens


# ── list_my_folder_shares (join → .all(), не scalars) ─────────────────────


@pytest.mark.asyncio
async def test_list_my_folder_shares_returns_rows():
    db = _make_db()
    rows = [(MagicMock(), "My folder")]
    db.execute.return_value = _result_rows(rows)

    result = await repo.list_my_folder_shares(db, uuid.uuid4())

    assert result == rows
    db.execute.assert_awaited_once()


# ── get_photo_share_token / get_folder_share_token ────────────────────────


@pytest.mark.asyncio
async def test_get_photo_share_token_returns_scalar():
    db = _make_db()
    tok = MagicMock()
    db.scalar.return_value = tok

    assert await repo.get_photo_share_token(db, uuid.uuid4()) is tok
    db.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_photo_share_token_returns_none():
    db = _make_db()
    db.scalar.return_value = None
    assert await repo.get_photo_share_token(db, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_get_folder_share_token_returns_scalar():
    db = _make_db()
    tok = MagicMock()
    db.scalar.return_value = tok

    assert await repo.get_folder_share_token(db, uuid.uuid4()) is tok
    db.scalar.assert_awaited_once()


# ── fetch_photo_share_token_by_token (execute → scalar_one_or_none) ───────


@pytest.mark.asyncio
async def test_fetch_photo_share_token_by_token_found():
    db = _make_db()
    tok = MagicMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = tok
    db.execute.return_value = res

    assert await repo.fetch_photo_share_token_by_token(db, "abc") is tok
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_photo_share_token_by_token_not_found():
    db = _make_db()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    db.execute.return_value = res

    assert await repo.fetch_photo_share_token_by_token(db, "missing") is None


# ── scalar_folder_share_token_by_token ─────────────────────────────────────


@pytest.mark.asyncio
async def test_scalar_folder_share_token_by_token_found():
    db = _make_db()
    tok = MagicMock()
    db.scalar.return_value = tok

    assert await repo.scalar_folder_share_token_by_token(db, "xyz") is tok
    db.scalar.assert_awaited_once()
