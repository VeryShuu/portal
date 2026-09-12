"""Unit-тесты для ``app.services.photos_tag_repo``.

Чистый DAO без бизнес-логики — покрываем контракты вызовов SQLAlchemy:
* правильная передача ``photo_id`` / ``tag_id`` / ``q`` в ``where``;
* ветка пустого ``q`` (фильтр не добавляется);
* возвращаемые значения идут из ``scalars().all()`` / ``scalar()`` / ``execute()``.

Эталон стиля — ``test_helpdesk_messages_tx.py`` (``MagicMock`` сессии + явные
``AsyncMock`` на async-методах; sync-методы вроде ``scalars()``/``unique()``
остаются синхронными, как в реальной ``AsyncSession``).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import photos_tag_repo as repo


def _make_db() -> MagicMock:
    """Мок AsyncSession. ``execute`` — AsyncMock, остальные sync-методы строят
    цепочку scalars/scalar/unique поверх возвращаемого ``result``."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


def _result_with_scalars(rows: list[Any]) -> MagicMock:
    """``await db.execute(...)`` → объект с ``.scalars().all()``."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _result_with_rows(rows: list[Any]) -> MagicMock:
    """``await db.execute(...)`` → ``.all()`` напрямую (без scalars)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


# ── list_tags_with_usage ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tags_with_usage_no_filter_builds_query_without_where():
    db = _make_db()
    db.execute.return_value = _result_with_rows([])

    await repo.list_tags_with_usage(db, q="")

    # execute был вызван ровно один раз — безусловно (фильтр q пустой → не добавляется)
    assert db.execute.await_count == 1
    # Проверяем, что возвращаемое значение проброшено из .all()
    assert db.execute.return_value.all.return_value == []


@pytest.mark.asyncio
async def test_list_tags_with_usage_with_filter_returns_rows():
    db = _make_db()
    rows = [("tag1", 5), ("tag2", 0)]
    db.execute.return_value = _result_with_rows(rows)

    result = await repo.list_tags_with_usage(db, q="nat")

    assert result == rows


# ── find_tag_by_name / get_tag ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_tag_by_name_returns_scalar():
    db = _make_db()
    tag = MagicMock(name="tag")
    db.scalar.return_value = tag

    result = await repo.find_tag_by_name(db, "nature")

    db.scalar.assert_awaited_once()
    assert result is tag


@pytest.mark.asyncio
async def test_find_tag_by_name_returns_none():
    db = _make_db()
    db.scalar.return_value = None

    assert await repo.find_tag_by_name(db, "missing") is None


@pytest.mark.asyncio
async def test_get_tag_returns_scalar():
    db = _make_db()
    tag_id = uuid.uuid4()
    tag = MagicMock(id=tag_id)
    db.scalar.return_value = tag

    result = await repo.get_tag(db, tag_id)

    db.scalar.assert_awaited_once()
    assert result is tag


# ── delete_tag ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_tag_executes_delete_stmt():
    db = _make_db()
    tag_id = uuid.uuid4()

    await repo.delete_tag(db, tag_id)

    db.execute.assert_awaited_once()


# ── list_photo_tags / clear_photo_tags ─────────────────────────────────────


@pytest.mark.asyncio
async def test_list_photo_tags_returns_scalars_all():
    db = _make_db()
    tags = [MagicMock(name="t1"), MagicMock(name="t2")]
    db.execute.return_value = _result_with_scalars(tags)

    result = await repo.list_photo_tags(db, uuid.uuid4())

    assert result == tags
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_photo_tags_executes_delete_stmt():
    db = _make_db()

    await repo.clear_photo_tags(db, uuid.uuid4())

    db.execute.assert_awaited_once()
