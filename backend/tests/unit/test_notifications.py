"""Unit-тесты для системы уведомлений Phase 4."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_notification(**kwargs):
    from app.models.notification import Notification

    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type="news_published",
        title="Test notification",
        body=None,
        link="/news/1",
        is_read=False,
    )
    defaults.update(kwargs)
    n = MagicMock(spec=Notification)
    for k, v in defaults.items():
        setattr(n, k, v)
    return n


# ── STREAM KEY ────────────────────────────────────────────────────────────────


def test_stream_key_format():
    from app.services.notifications import NOTIFICATIONS_STREAM_KEY

    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid))
    assert key == "notifications:12345678-1234-5678-1234-567812345678"


# ── _publish_to_stream ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_to_stream_calls_xadd():
    from app.services.notifications import _publish_to_stream

    redis = AsyncMock()
    notif = _make_notification()
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00+00:00"

    await _publish_to_stream(redis, user_id=notif.user_id, notification=notif)

    redis.xadd.assert_called_once()
    args, kwargs = redis.xadd.call_args
    key = args[0]
    assert str(notif.user_id) in key
    redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_publish_to_stream_handles_redis_error(caplog):
    from app.services.notifications import _publish_to_stream

    redis = AsyncMock()
    redis.xadd.side_effect = Exception("connection refused")
    notif = _make_notification()
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    await _publish_to_stream(redis, user_id=notif.user_id, notification=notif)
    # No exception propagated — fire-and-forget style


# ── notify_suggestion_reviewed ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_approve():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    user = MagicMock()
    user.id = uuid.uuid4()
    user.notify_inapp = True

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db,
            redis,
            suggestion_author_id=user.id,
            article_id=uuid.uuid4(),
            article_title="Тестовая статья",
            action="approve",
        )
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert "одобрена" in call_kwargs["title"]
        assert call_kwargs["type"] == "suggestion_reviewed"


@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_reject():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    user = MagicMock()
    user.id = uuid.uuid4()
    user.notify_inapp = True

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db,
            redis,
            suggestion_author_id=user.id,
            article_id=uuid.uuid4(),
            article_title="Тестовая статья",
            action="reject",
        )
        call_kwargs = mock_create.call_args.kwargs
        assert "отклонена" in call_kwargs["title"]


@pytest.mark.asyncio
async def test_notify_suggestion_reviewed_skips_if_no_user():
    from app.services.notifications import notify_suggestion_reviewed

    db = AsyncMock()
    redis = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_suggestion_reviewed(
            db,
            redis,
            suggestion_author_id=uuid.uuid4(),
            article_id=uuid.uuid4(),
            article_title="Статья",
            action="approve",
        )
        mock_create.assert_not_called()


# ── notify_users_news_published ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_users_news_published_targets_departments():
    from app.services.notifications import notify_users_news_published

    db = AsyncMock()
    redis = AsyncMock()

    user_it = MagicMock()
    user_it.id = uuid.uuid4()
    user_it.notify_inapp = True
    user_it.department = "IT"
    user_it.role = "reader"

    user_hr = MagicMock()
    user_hr.id = uuid.uuid4()
    user_hr.notify_inapp = True
    user_hr.department = "HR"
    user_hr.role = "reader"

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [user_it]
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_users_news_published(
            db,
            redis,
            news_id=uuid.uuid4(),
            news_title="IT Новость",
            target_departments=["IT"],
        )
        assert sent == 1
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["user_id"] == user_it.id


@pytest.mark.asyncio
async def test_notify_users_news_published_no_filter_notifies_all():
    from app.services.notifications import notify_users_news_published

    db = AsyncMock()
    redis = AsyncMock()

    users = [
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="IT", role="reader"),
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="HR", role="reader"),
        MagicMock(id=uuid.uuid4(), notify_inapp=True, department="Finance", role="editor"),
    ]

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = users
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_users_news_published(
            db,
            redis,
            news_id=uuid.uuid4(),
            news_title="Общая новость",
        )
        assert sent == 3
        assert mock_create.call_count == 3


# ── Email builder ─────────────────────────────────────────────────────────────


def test_build_news_email_html_contains_title():
    from app.worker.tasks.notifications import _build_news_email_html

    html, text = _build_news_email_html("Важная новость", "http://portal/news/1", "Мой портал")
    assert "Важная новость" in html
    assert "Мой портал" in html
    assert "http://portal/news/1" in html
    assert "Важная новость" in text


def test_build_suggestion_email_html_approve():
    from app.worker.tasks.notifications import _build_suggestion_email_html

    html, text = _build_suggestion_email_html("Статья А", "http://portal/kb/1", "approve", "Портал")
    assert "одобрена" in html
    assert "одобрена" in text
    assert "#27ae60" in html


def test_build_suggestion_email_html_reject():
    from app.worker.tasks.notifications import _build_suggestion_email_html

    html, text = _build_suggestion_email_html("Статья Б", "http://portal/kb/2", "reject", "Портал")
    assert "отклонена" in html
    assert "#c0392b" in html


# ── SSE generator edge cases ──────────────────────────────────────────────────


def test_notifications_stream_key_per_user():
    from app.services.notifications import NOTIFICATIONS_STREAM_KEY

    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    key1 = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid1))
    key2 = NOTIFICATIONS_STREAM_KEY.format(user_id=str(uid2))
    assert key1 != key2


# ── get_unread_count ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_unread_count_returns_scalar():
    from app.services.notifications import get_unread_count

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = 7
    db.execute.return_value = execute_result

    count = await get_unread_count(db, uuid.uuid4())
    assert count == 7


# ── SSE constants & exponential backoff ──────────────────────────────────────


def test_sse_global_cap_constant_exists():
    from app.api.notifications import _SSE_MAX_CONNECTIONS_GLOBAL

    assert _SSE_MAX_CONNECTIONS_GLOBAL > 0


def test_sse_global_key_constant_exists():
    from app.api.notifications import _SSE_GLOBAL_CONN_KEY

    assert isinstance(_SSE_GLOBAL_CONN_KEY, str)
    assert "global" in _SSE_GLOBAL_CONN_KEY


def test_sse_backoff_constants_are_sane():
    from app.api.notifications import _SSE_BACKOFF_BASE, _SSE_BACKOFF_MAX

    assert 0 < _SSE_BACKOFF_BASE <= 5
    assert _SSE_BACKOFF_MAX >= _SSE_BACKOFF_BASE


def test_sse_backoff_formula_grows_exponentially():
    from app.api.notifications import _SSE_BACKOFF_BASE, _SSE_BACKOFF_MAX

    backoffs = [
        min(_SSE_BACKOFF_BASE * (2 ** (n - 1)), _SSE_BACKOFF_MAX)
        for n in range(1, 8)
    ]
    for i in range(len(backoffs) - 1):
        assert backoffs[i + 1] >= backoffs[i]

    assert backoffs[-1] == _SSE_BACKOFF_MAX


def test_sse_lua_script_has_two_keys():
    from app.api.notifications import _LUA_CONN_ADD

    assert "KEYS[1]" in _LUA_CONN_ADD
    assert "KEYS[2]" in _LUA_CONN_ADD
    assert "ARGV[5]" in _LUA_CONN_ADD


def test_sse_lua_script_returns_negative_on_limits():
    from app.api.notifications import _LUA_CONN_ADD

    assert "return -1" in _LUA_CONN_ADD
    assert "return -2" in _LUA_CONN_ADD


@pytest.mark.asyncio
async def test_sse_generator_cleanup_removes_from_global_key():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.api.notifications import _SSE_GLOBAL_CONN_KEY, _sse_generator

    request = MagicMock()
    request.headers.get.return_value = "$"
    request.is_disconnected = AsyncMock(return_value=True)

    redis = AsyncMock()
    redis.zrem = AsyncMock()

    user_id = uuid.uuid4()
    connection_id = "testconn123"

    gen = _sse_generator(request, redis, user_id, connection_id)
    async for _ in gen:
        pass

    zrem_calls = [str(c) for c in redis.zrem.call_args_list]
    assert any(_SSE_GLOBAL_CONN_KEY in c for c in zrem_calls)


# ── SSE max_connections per user ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_11th_connection_returns_429_per_user(app, user_factory):
    """11-й коннект от одного пользователя должен вернуть 429 (per-user limit)."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user, get_redis

    user = user_factory(role="reader")

    async def _fake_user():
        return user

    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=-1)

    async def _fake_redis():
        return fake_redis

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_redis] = _fake_redis

    _CSRF_TOKEN = "test-csrf-token-for-unit-tests"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
        ) as ac:
            r = await ac.get("/api/v1/notifications/stream")
        assert r.status_code == 429
        assert "per user" in r.json().get("detail", "")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_sse_global_limit_returns_429(app, user_factory):
    """При глобальном лимите SSE должен вернуть 429 (global limit)."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user, get_redis

    user = user_factory(role="reader")

    async def _fake_user():
        return user

    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=-2)

    async def _fake_redis():
        return fake_redis

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_redis] = _fake_redis

    _CSRF_TOKEN = "test-csrf-token-for-unit-tests"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": _CSRF_TOKEN},
            cookies={"XSRF-TOKEN": _CSRF_TOKEN},
        ) as ac:
            r = await ac.get("/api/v1/notifications/stream")
        assert r.status_code == 429
        assert "limit" in r.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_sse_lua_script_constants():
    """Константы Lua-скрипта соответствуют ограничениям из spec."""
    from app.api.notifications import (
        _SSE_MAX_CONNECTIONS_GLOBAL,
        _SSE_MAX_CONNECTIONS_PER_USER,
    )

    assert _SSE_MAX_CONNECTIONS_PER_USER == 10, "Per-user limit must be 10 per spec"
    assert _SSE_MAX_CONNECTIONS_GLOBAL >= 100, "Global limit must be at least 100"
