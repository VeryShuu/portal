"""Unit-тесты services/news/likes.py.

Покрытие (db мокается, проверяется control-flow + возвращаемое состояние):
- like_news: новая строка → инкремент счётчика, liked_by_me=True
- like_news: повторный лайк (ON CONFLICT, rowcount=0) → без инкремента (идемпотентность)
- unlike_news: строка удалена → декремент, liked_by_me=False
- unlike_news: лайка не было (rowcount=0) → без декремента
- is_liked_by: True/False по наличию строки
- get_liked_news_ids: пустой вход → без запроса; иначе множество id
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.news import likes as likes_svc

NEWS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _result(*, rowcount: int = 0, scalar=None, first=None, scalars_all=None) -> MagicMock:
    r = MagicMock()
    r.rowcount = rowcount
    r.scalar_one = MagicMock(return_value=scalar)
    r.first = MagicMock(return_value=first)
    sc = MagicMock()
    sc.all = MagicMock(return_value=scalars_all or [])
    r.scalars = MagicMock(return_value=sc)
    return r


def _make_db(execute_results: list) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.commit = AsyncMock()
    return db


class TestLikeNews:
    @pytest.mark.asyncio
    async def test_new_like_increments_counter(self):
        db = _make_db([_result(rowcount=1), _result(rowcount=1), _result(scalar=5)])

        state = await likes_svc.like_news(db, news_id=NEWS_ID, user_id=USER_ID)

        assert state.like_count == 5
        assert state.liked_by_me is True
        assert db.execute.await_count == 3  # insert + update + count
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_like_is_idempotent(self):
        db = _make_db([_result(rowcount=0), _result(scalar=5)])

        state = await likes_svc.like_news(db, news_id=NEWS_ID, user_id=USER_ID)

        assert state.like_count == 5
        assert state.liked_by_me is True
        assert db.execute.await_count == 2  # insert (no-op) + count, без update


class TestUnlikeNews:
    @pytest.mark.asyncio
    async def test_existing_like_decrements_counter(self):
        db = _make_db([_result(rowcount=1), _result(rowcount=1), _result(scalar=4)])

        state = await likes_svc.unlike_news(db, news_id=NEWS_ID, user_id=USER_ID)

        assert state.like_count == 4
        assert state.liked_by_me is False
        assert db.execute.await_count == 3  # delete + update + count
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_like_is_noop(self):
        db = _make_db([_result(rowcount=0), _result(scalar=4)])

        state = await likes_svc.unlike_news(db, news_id=NEWS_ID, user_id=USER_ID)

        assert state.like_count == 4
        assert state.liked_by_me is False
        assert db.execute.await_count == 2  # delete (no-op) + count, без update


class TestIsLikedBy:
    @pytest.mark.asyncio
    async def test_true_when_row_present(self):
        db = _make_db([_result(first=(uuid.uuid4(),))])
        assert await likes_svc.is_liked_by(db, news_id=NEWS_ID, user_id=USER_ID) is True

    @pytest.mark.asyncio
    async def test_false_when_absent(self):
        db = _make_db([_result(first=None)])
        assert await likes_svc.is_liked_by(db, news_id=NEWS_ID, user_id=USER_ID) is False


class TestGetLikedNewsIds:
    @pytest.mark.asyncio
    async def test_empty_input_skips_query(self):
        db = _make_db([])
        result = await likes_svc.get_liked_news_ids(db, user_id=USER_ID, news_ids=[])
        assert result == set()
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_set_of_ids(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        db = _make_db([_result(scalars_all=[a, b])])
        result = await likes_svc.get_liked_news_ids(db, user_id=USER_ID, news_ids=[a, b])
        assert result == {a, b}
