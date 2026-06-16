"""Unit-тесты для системы уведомлений Phase 4."""

from __future__ import annotations

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
    args, _kwargs = redis.xadd.call_args
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
    execute_result.scalars.return_value.all.return_value = [user_it.id]
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

    user_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = user_ids
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


def test_sse_global_cap_in_system_settings():
    from app.core.system_config import SystemSettings

    defaults = SystemSettings()
    assert defaults.sse_max_connections_global > 0
    assert defaults.sse_max_connections_per_user > 0


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

    backoffs = [min(_SSE_BACKOFF_BASE * (2 ** (n - 1)), _SSE_BACKOFF_MAX) for n in range(1, 8)]
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
    from unittest.mock import AsyncMock, MagicMock

    from app.api.notifications import _SSE_GLOBAL_CONN_KEY, _sse_generator

    request = MagicMock()
    request.headers.get.return_value = "$"
    request.is_disconnected = AsyncMock(return_value=True)

    redis = AsyncMock()
    redis.zrem = AsyncMock()

    user_id = uuid.uuid4()
    connection_id = "testconn123"

    gen = _sse_generator(request, redis, user_id, connection_id, None)
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

    csrf_token = "test-csrf-token-for-unit-tests"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
            cookies={"XSRF-TOKEN": csrf_token},
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

    csrf_token = "test-csrf-token-for-unit-tests"
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
            cookies={"XSRF-TOKEN": csrf_token},
        ) as ac:
            r = await ac.get("/api/v1/notifications/stream")
        assert r.status_code == 429
        assert "limit" in r.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_redis, None)


def test_sse_lua_script_constants():
    """SSE limits are configurable via system settings with sensible defaults."""
    from app.core.system_config import SystemSettings

    defaults = SystemSettings()
    assert defaults.sse_max_connections_per_user == 10, "Per-user default must be 10"
    assert defaults.sse_max_connections_global >= 100, "Global default must be at least 100"


# ── create_notification ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_notification_adds_to_db_and_returns_publish():
    from app.services.notifications import create_notification

    db = AsyncMock()
    db.add = MagicMock()
    redis = AsyncMock()

    user_id = uuid.uuid4()
    notif = _make_notification(user_id=user_id, type="news_published", title="Hello")
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    db.flush = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    publish_fn = await create_notification(
        db,
        redis,
        user_id=user_id,
        type="news_published",
        title="Hello",
        body="Body text",
        link="/news/42",
    )

    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert callable(publish_fn)


@pytest.mark.asyncio
async def test_create_notification_publish_fn_calls_stream():
    from app.services.notifications import create_notification

    db = AsyncMock()
    db.add = MagicMock()
    redis = AsyncMock()

    user_id = uuid.uuid4()
    notif = _make_notification(user_id=user_id)
    notif.created_at = MagicMock()
    notif.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    with patch("app.services.notifications._publish_to_stream", new=AsyncMock()) as mock_pub:
        publish_fn = await create_notification(
            db, redis, user_id=user_id, type="test", title="Title"
        )
        await publish_fn()
        mock_pub.assert_awaited_once()


# ── notify_admins_new_feedback ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_admins_new_feedback_sends_to_admins():
    from app.services.notifications import notify_admins_new_feedback

    db = AsyncMock()
    redis = AsyncMock()

    admin_id1 = uuid.uuid4()
    admin_id2 = uuid.uuid4()
    author_id = uuid.uuid4()

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [admin_id1, admin_id2]
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_admins_new_feedback(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            author_id=author_id,
            author_name="Alice",
            category="bug",
        )

    assert sent == 2
    assert mock_create.call_count == 2
    call_kwargs = mock_create.call_args_list[0].kwargs
    assert "Alice" in call_kwargs["title"]
    assert call_kwargs["type"] == "feedback_new"


@pytest.mark.asyncio
async def test_notify_admins_new_feedback_no_admins_returns_zero():
    from app.services.notifications import notify_admins_new_feedback

    db = AsyncMock()
    redis = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        sent = await notify_admins_new_feedback(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            author_id=None,
            author_name="Bob",
            category="other",
        )

    assert sent == 0
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_new_feedback_category_label():
    from app.services.notifications import notify_admins_new_feedback

    db = AsyncMock()
    redis = AsyncMock()
    admin_id = uuid.uuid4()

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [admin_id]
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_admins_new_feedback(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            author_id=None,
            author_name="User",
            category="suggestion",
        )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["body"] == "Предложение"


# ── notify_user_feedback_reply ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_user_feedback_reply_sends_to_user():
    from app.services.notifications import notify_user_feedback_reply

    db = AsyncMock()
    redis = AsyncMock()
    user_id = uuid.uuid4()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user_id
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_user_feedback_reply(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            user_id=user_id,
            admin_name="Admin A",
        )

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert "Admin A" in call_kwargs["body"]
    assert call_kwargs["type"] == "feedback_reply"


@pytest.mark.asyncio
async def test_notify_user_feedback_reply_skips_if_no_user():
    from app.services.notifications import notify_user_feedback_reply

    db = AsyncMock()
    redis = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_user_feedback_reply(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            admin_name="Admin",
        )

    mock_create.assert_not_called()


# ── notify_user_feedback_status_changed ───────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_user_feedback_status_changed_only_on_closed():
    from app.services.notifications import notify_user_feedback_status_changed

    db = AsyncMock()
    redis = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_user_feedback_status_changed(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            new_status="open",
        )

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_notify_user_feedback_status_changed_closed_notifies_user():
    from app.services.notifications import notify_user_feedback_status_changed

    db = AsyncMock()
    redis = AsyncMock()
    user_id = uuid.uuid4()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user_id
    db.execute.return_value = execute_result
    db.commit = AsyncMock()

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_user_feedback_status_changed(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            user_id=user_id,
            new_status="closed",
        )

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["type"] == "feedback_closed"


@pytest.mark.asyncio
async def test_notify_user_feedback_status_changed_skips_if_no_user():
    from app.services.notifications import notify_user_feedback_status_changed

    db = AsyncMock()
    redis = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    with patch("app.services.notifications.create_notification", new=AsyncMock()) as mock_create:
        await notify_user_feedback_status_changed(
            db,
            redis,
            feedback_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            new_status="closed",
        )

    mock_create.assert_not_called()


# ── #B-6: e2e realtime photo_processed (publish → SSE) ───────────────────────


@pytest.mark.asyncio
async def test_publish_photo_processed_emits_sse_event_b6():
    """E2E realtime (#B-6): publish_photo_processed → _sse_generator → SSE frame.

    Wires the worker-side publisher (``photos_realtime.publish_photo_processed``)
    into the same Redis stream consumed by ``_sse_generator`` and asserts that
    the resulting SSE payload carries ``event: photo_processed`` and the
    expected fields. Replaces two prior isolated tests (xadd alone / SSE alone).
    """
    from app.api.notifications import _sse_generator
    from app.services.photos_realtime import publish_photo_processed

    photo_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    user_id = uuid.uuid4()
    blurhash = "L6PZfSi_.AyE_3t7t7R**0o#DgR4"

    captured: dict = {}

    async def fake_xadd(key, fields, **_kwargs):
        captured["key"] = key
        captured["fields"] = fields
        return b"1-0"

    redis_pub = AsyncMock()
    redis_pub.xadd = fake_xadd

    await publish_photo_processed(
        redis_pub,
        photo_id=photo_id,
        folder_id=folder_id,
        blurhash=blurhash,
    )

    assert captured.get("key") == "notifications:photos"
    assert captured["fields"]["type"] == "photo_processed"
    assert captured["fields"]["photo_id"] == str(photo_id)

    poll_state = {"n": 0}

    async def fake_xread(streams, count=10, block=0):
        poll_state["n"] += 1
        poll_state.setdefault("calls", []).append((dict(streams), count, block))
        if "notifications:photos" in streams and poll_state["n"] <= 3:
            return [("notifications:photos", [("1-0", captured["fields"])])]
        return []

    redis_sse = AsyncMock()
    redis_sse.xread = fake_xread
    redis_sse.zrem = AsyncMock()
    redis_sse.expire = AsyncMock()

    pipe = AsyncMock()
    pipe.zadd = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock()
    pipe_cm = MagicMock()
    pipe_cm.__aenter__ = AsyncMock(return_value=pipe)
    pipe_cm.__aexit__ = AsyncMock(return_value=None)
    redis_sse.pipeline = MagicMock(return_value=pipe_cm)

    request = MagicMock()
    request.headers.get.return_value = "$|$|0"
    disc_state = {"n": 0}

    async def fake_disconnected():
        disc_state["n"] += 1
        return disc_state["n"] > 1

    request.is_disconnected = fake_disconnected

    frames: list[str] = []
    async for frame in _sse_generator(request, redis_sse, user_id, "conn-b6", None):
        frames.append(frame)

    body = "".join(frames)
    assert "event: photo_processed" in body
    assert str(photo_id) in body
    assert str(folder_id) in body
    assert "photo_processed" in body
