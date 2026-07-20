"""Unit-тесты для ``app.api.news.comments_repo``.

Контракты:
* ``count_active_comments`` — ``scalar_one()`` (COUNT всегда возвращает одну строку);
* ``list_comments`` — ``scalars().all()`` c limit/offset;
* ``get_comment_authors`` — короткое замыкание на пустом ``author_ids`` (без execute);
* ``get_comment`` — ``scalar_one_or_none()`` с фильтром по (id, news_id);
* ``increment`` / ``decrement`` — выполняют UPDATE с ``comment_count + 1`` /
  ``greatest(comment_count - 1, 0)`` (защита от ухода в минус при гонке).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.news import comments_repo as repo


def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _result_scalar(value: Any) -> MagicMock:
    res = MagicMock()
    res.scalar_one.return_value = value
    return res


def _result_scalars(rows: list[Any]) -> MagicMock:
    res = MagicMock()
    res.scalars.return_value.all.return_value = rows
    return res


def _result_one_or_none(value: Any) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


# ── count_active_comments ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_active_comments_returns_scalar_one():
    db = _make_db()
    db.execute.return_value = _result_scalar(42)

    assert await repo.count_active_comments(db, uuid.uuid4()) == 42
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_count_active_comments_zero():
    db = _make_db()
    db.execute.return_value = _result_scalar(0)

    assert await repo.count_active_comments(db, uuid.uuid4()) == 0


# ── list_comments ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_comments_returns_scalars():
    db = _make_db()
    comments = [MagicMock(), MagicMock()]
    db.execute.return_value = _result_scalars(comments)

    result = await repo.list_comments(db, uuid.uuid4(), limit=10, offset=0)

    assert result == comments
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_comments_empty():
    db = _make_db()
    db.execute.return_value = _result_scalars([])

    assert await repo.list_comments(db, uuid.uuid4(), limit=10, offset=20) == []


# ── get_comment_authors ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_comment_authors_empty_input_short_circuits_without_execute():
    """Контракт: пустой ``author_ids`` → нет запроса в БД (ранний return {})."""
    db = _make_db()

    result = await repo.get_comment_authors(db, set())

    assert result == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_comment_authors_returns_dict_by_id():
    db = _make_db()
    u1, u2 = MagicMock(), MagicMock()
    u1.id = uuid.uuid4()
    u2.id = uuid.uuid4()
    res = MagicMock()
    res.scalars.return_value = [u1, u2]
    db.execute.return_value = res

    result = await repo.get_comment_authors(db, {u1.id, u2.id})

    assert result == {u1.id: u1, u2.id: u2}
    db.execute.assert_awaited_once()


# ── get_comment ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_comment_found():
    db = _make_db()
    comment = MagicMock()
    db.execute.return_value = _result_one_or_none(comment)

    result = await repo.get_comment(db, news_id=uuid.uuid4(), comment_id=uuid.uuid4())

    assert result is comment
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_comment_returns_none_on_mismatch():
    db = _make_db()
    db.execute.return_value = _result_one_or_none(None)

    assert await repo.get_comment(db, news_id=uuid.uuid4(), comment_id=uuid.uuid4()) is None


# ── increment_comment_count / decrement_comment_count ─────────────────────


@pytest.mark.asyncio
async def test_increment_comment_count_runs_update():
    db = _make_db()

    await repo.increment_comment_count(db, uuid.uuid4())

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_decrement_comment_count_runs_update_with_greatest():
    """decrement использует ``greatest(comment_count - 1, 0)`` — защита от ухода
    в минус при гонке между decrement и soft-delete в параллельных транзакциях.
    Контракт: выполняется UPDATE, ``comment_count`` не может стать < 0."""
    db = _make_db()

    await repo.decrement_comment_count(db, uuid.uuid4())

    db.execute.assert_awaited_once()
    # Проверяем, что в сформированном statement есть greatest (защита от регресса
    # на наивный ``comment_count - 1`` без floor).
    stmt = db.execute.await_args.args[0]
    stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "greatest" in stmt_str.lower()
