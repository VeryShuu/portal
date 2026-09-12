"""Redis-кеш сводного дашборда аналитики (audit L2).

Проверяет контракт кеша в ``GET /analytics/dashboard``: cache-hit не ходит в БД,
cache-miss наполняет кеш с TTL, сбой Redis не роняет эндпоинт, ключ включает
параметр ``days``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_redis
from app.core.constants import ANALYTICS_DASHBOARD_CACHE_TTL_SECONDS

_CACHED_PAYLOAD = {
    "generated_at": "2026-08-19T10:00:00+00:00",
    "users": {"total": 42, "active_30d": 7, "active_1h": 3, "new_30d": 1},
    "content": {"news_published_30d": 5, "kb_articles_published_30d": 2},
    "activity": {"audit_events_24h": 9, "logins_24h": 4, "wau_7d": 6, "mau_30d": 8},
    "series": {
        "daily_logins_14d": [],
        "daily_publications_14d": [],
        "daily_active_users": [],
        "daily_uploads": [],
    },
    "approvals": {
        "approved": 0,
        "rejected": 0,
        "active_users": 0,
        "last_event_at": None,
        "daily": [],
    },
}


def _make_db_session() -> MagicMock:
    """Сессия с нулевой статистикой и записью факта каждого execute."""
    scalar_row = MagicMock(
        total_users=0,
        active_users_30d=0,
        active_users_1h=0,
        new_users_30d=0,
        published_news_30d=0,
        published_articles_30d=0,
        audit_24h=0,
        logins_24h=0,
        wau_7d=0,
        mau_30d=0,
        # approvals-блок дашборда (fetch_approvals_usage -> .one())
        approved=0,
        rejected=0,
        active_users=0,
        last_event_at=None,
    )
    result = MagicMock()
    result.one = MagicMock(return_value=scalar_row)
    result.all = MagicMock(return_value=[])
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _make_redis(get_return: str | None = None, get_raises: bool = False) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(
        side_effect=RuntimeError("redis down") if get_raises else None,
        return_value=None if get_raises else get_return,
    )
    redis.set = AsyncMock(return_value=True)
    return redis


def _authed_app(app, user_factory, session: MagicMock, redis: MagicMock):
    user = user_factory(role="admin")

    async def _fake_user():
        return user

    async def _fake_db():
        yield session

    async def _fake_redis():
        return redis

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_redis] = _fake_redis
    return app


async def _get(app, path: str = "/api/v1/analytics/dashboard"):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"Origin": "http://test"}
    ) as ac:
        return await ac.get(path)


async def test_cache_hit_returns_cached_and_skips_db(app, user_factory):
    session = _make_db_session()
    redis = _make_redis(get_return=json.dumps(_CACHED_PAYLOAD))
    _authed_app(app, user_factory, session, redis)

    r = await _get(app)

    assert r.status_code == 200
    assert r.json()["users"]["total"] == 42
    session.execute.assert_not_awaited()
    redis.set.assert_not_awaited()


async def test_cache_miss_computes_and_populates_cache(app, user_factory):
    session = _make_db_session()
    redis = _make_redis(get_return=None)
    _authed_app(app, user_factory, session, redis)

    r = await _get(app)

    assert r.status_code == 200
    assert session.execute.await_count == 7  # scalars + 4 daily-серии + approvals (итоги, ряд)
    redis.set.assert_awaited_once()
    key, payload = redis.set.await_args.args[0], redis.set.await_args.args[1]
    assert key == "analytics:dashboard:v2:14"
    assert redis.set.await_args.kwargs["ex"] == ANALYTICS_DASHBOARD_CACHE_TTL_SECONDS
    assert json.loads(payload)["users"]["total"] == 0


async def test_cache_key_reflects_days_param(app, user_factory):
    session = _make_db_session()
    redis = _make_redis(get_return=None)
    _authed_app(app, user_factory, session, redis)

    r = await _get(app, "/api/v1/analytics/dashboard?days=30")

    assert r.status_code == 200
    assert redis.set.await_args.args[0] == "analytics:dashboard:v2:30"


async def test_redis_read_failure_still_serves_from_db(app, user_factory):
    session = _make_db_session()
    redis = _make_redis(get_raises=True)
    _authed_app(app, user_factory, session, redis)

    r = await _get(app)

    assert r.status_code == 200
    assert session.execute.await_count == 7


async def test_redis_write_failure_still_serves_response(app, user_factory):
    session = _make_db_session()
    redis = _make_redis(get_return=None)
    redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    _authed_app(app, user_factory, session, redis)

    r = await _get(app)

    assert r.status_code == 200
    assert r.json()["users"]["total"] == 0
