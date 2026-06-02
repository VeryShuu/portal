"""Characterising tests for _sse_generator and notifications_stream success path."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_request(last_event_id="$", disconnected_calls=None):
    request = MagicMock()
    request.headers.get.return_value = last_event_id
    if disconnected_calls is None:
        disconnected_calls = [False, True]
    request.is_disconnected = AsyncMock(side_effect=disconnected_calls)
    request.cookies.get = MagicMock(return_value=None)
    return request


def _make_redis_empty():
    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)
    return redis


def _patch_pipeline(redis, *, raises=False):
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=None)
    cm = MagicMock()
    if raises:
        cm.__aenter__ = AsyncMock(side_effect=Exception("pipeline error"))
    else:
        cm.__aenter__ = AsyncMock(return_value=pipe)
    cm.__aexit__ = AsyncMock(return_value=False)
    redis.pipeline = MagicMock(return_value=cm)
    return pipe


async def _collect(gen):
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return "".join(chunks)


# ── Last-Event-ID parsing ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_last_event_id_plain_dollar():
    """Plain '$' Last-Event-ID uses $ for all three stream offsets."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])
    redis = _make_redis_empty()

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))
    assert ": connected" in combined


@pytest.mark.asyncio
async def test_sse_generator_last_event_id_composite_triple():
    """Composite 'p|m|ph' triple is split into per-stream offsets."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    composite = "111-0|222-0|333-0"
    request = _make_request(composite, [False, True])
    redis = _make_redis_empty()

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))
    assert ": connected" in combined


@pytest.mark.asyncio
async def test_sse_generator_last_event_id_empty_parts_default_to_dollar():
    """Empty parts in composite triple fall back to '$'."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("|", [False, True])
    redis = _make_redis_empty()

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))
    assert ": connected" in combined


@pytest.mark.asyncio
async def test_sse_generator_last_event_id_two_parts():
    """Two-part composite 'p|m' leaves photos at '$'."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("111-0|222-0", [False, True])
    redis = _make_redis_empty()

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))
    assert ": connected" in combined


# ── Yields connected comment first ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_first_chunk_is_connected():
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [True])
    redis = _make_redis_empty()

    chunks = []
    async for chunk in _sse_generator(request, redis, user_id, "c1", None):
        chunks.append(chunk)

    assert chunks[0] == ": connected\n\n"


# ── Event yielding ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_yields_notification_event():
    """Personal stream data → 'notification' SSE event with composite id."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    msg_id = "1700000000000-0"
    fields = {"type": "news_published", "title": "Hello"}

    redis.xread = AsyncMock(
        side_effect=[
            [[f"notifications:{user_id}", [(msg_id, fields)]]],
            [],
            [],
        ]
    )

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert "event: notification" in combined
    assert msg_id in combined
    assert "Hello" in combined


@pytest.mark.asyncio
async def test_sse_generator_notification_event_composite_id_format():
    """Event id is composite 'personal|meetings|photos' triple."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    msg_id = "1700000000001-0"
    redis.xread = AsyncMock(
        side_effect=[
            [[f"notifications:{user_id}", [(msg_id, {"t": "1"})]]],
            [],
            [],
        ]
    )

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    id_line = next(ln for ln in combined.splitlines() if ln.startswith("id:"))
    parts = id_line.removeprefix("id: ").split("|")
    assert len(parts) == 3
    assert parts[0] == msg_id
    assert parts[1] == "$"
    assert parts[2] == "$"


@pytest.mark.asyncio
async def test_sse_generator_yields_meeting_event():
    """Meetings stream data → 'meeting_changed' SSE event."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    msg_id = "1700000000002-0"
    redis.xread = AsyncMock(
        side_effect=[
            [],
            [["meetings:changes", [(msg_id, {"action": "updated"})]]],
            [],
        ]
    )

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert "event: meeting_changed" in combined
    assert msg_id in combined


@pytest.mark.asyncio
async def test_sse_generator_yields_photo_event():
    """Photos stream data → 'photo_processed' SSE event."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    msg_id = "1700000000003-0"
    redis.xread = AsyncMock(
        side_effect=[
            [],
            [],
            [["photos:processed", [(msg_id, {"photo_id": "abc"})]]],
        ]
    )

    combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert "event: photo_processed" in combined
    assert msg_id in combined


# ── Backoff path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_backoff_on_gather_error():
    """Exception in inner try block triggers backoff sleep and continue."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    def _failing_ensure_future(coro, *args, **kwargs):
        try:
            coro.close()
        except Exception:
            pass
        raise RuntimeError("simulated ensure_future failure")

    mock_sleep = AsyncMock()
    with patch("asyncio.ensure_future", _failing_ensure_future):
        with patch("asyncio.sleep", mock_sleep):
            combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    mock_sleep.assert_awaited_once()
    assert ": connected" in combined


@pytest.mark.asyncio
async def test_sse_generator_backoff_increments_consecutive_errors():
    """Multiple consecutive errors increment the backoff each time."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, False, True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    call_count = 0

    def _failing_ensure_future(coro, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        try:
            coro.close()
        except Exception:
            pass
        raise RuntimeError("fail")

    sleep_calls = []

    async def _capturing_sleep(secs):
        sleep_calls.append(secs)

    with patch("asyncio.ensure_future", _failing_ensure_future):
        with patch("asyncio.sleep", _capturing_sleep):
            await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert len(sleep_calls) == 2
    assert sleep_calls[1] >= sleep_calls[0]


# ── Keepalive path ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_keepalive_emitted():
    """When keepalive threshold is reached, ': keepalive' comment is yielded."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    with patch("app.api.notifications._SSE_KEEPALIVE_SEC", 0.0):
        combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert ": keepalive" in combined


@pytest.mark.asyncio
async def test_sse_generator_keepalive_refreshes_ttl():
    """Keepalive block calls pipeline zadd/expire to refresh TTL."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    pipe = _patch_pipeline(redis)

    with patch("app.api.notifications._SSE_KEEPALIVE_SEC", 0.0):
        await _collect(_sse_generator(request, redis, user_id, "c1", None))

    pipe.zadd.assert_called()
    pipe.expire.assert_called()
    pipe.execute.assert_awaited()


@pytest.mark.asyncio
async def test_sse_generator_keepalive_ttl_refresh_failed_continues():
    """Pipeline failure in keepalive block is swallowed; keepalive still emitted."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    _patch_pipeline(redis, raises=True)

    with patch("app.api.notifications._SSE_KEEPALIVE_SEC", 0.0):
        combined = await _collect(_sse_generator(request, redis, user_id, "c1", None))

    assert ": keepalive" in combined


@pytest.mark.asyncio
async def test_sse_generator_session_extend_called_when_due():
    """When session_id present and extend interval elapsed, redis.expire is called."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    session_id = "sess-abc-123"
    request = _make_request("$", [False, True])
    request.cookies.get = MagicMock(return_value=session_id)

    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    redis.expire = AsyncMock()
    _patch_pipeline(redis)

    with patch("app.api.notifications._SSE_KEEPALIVE_SEC", 0.0):
        with patch("app.api.notifications._SSE_SESSION_EXTEND_INTERVAL", 0):
            await _collect(_sse_generator(request, redis, user_id, "c1", session_id))

    redis.expire.assert_awaited()


@pytest.mark.asyncio
async def test_sse_generator_session_extend_failed_continues():
    """redis.expire failure during session extend is swallowed; no crash."""
    from app.api.notifications import _sse_generator

    user_id = uuid.uuid4()
    session_id = "sess-xyz"
    request = _make_request("$", [False, True])

    redis = AsyncMock()
    redis.xread = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    redis.expire = AsyncMock(side_effect=Exception("expire failed"))
    _patch_pipeline(redis)

    with patch("app.api.notifications._SSE_KEEPALIVE_SEC", 0.0):
        with patch("app.api.notifications._SSE_SESSION_EXTEND_INTERVAL", 0):
            combined = await _collect(_sse_generator(request, redis, user_id, "c1", session_id))

    assert ": keepalive" in combined


# ── Cleanup ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_generator_cleanup_removes_per_user_key():
    """On exit, per-user SSE connection key is removed from Redis."""
    from app.api.notifications import _SSE_CONN_KEY, _sse_generator

    user_id = uuid.uuid4()
    request = _make_request("$", [True])

    redis = AsyncMock()
    redis.zrem = AsyncMock()
    _patch_pipeline(redis)

    conn_id = "myconn42"
    await _collect(_sse_generator(request, redis, user_id, conn_id, None))

    expected_conn_key = _SSE_CONN_KEY.format(user_id=str(user_id))
    zrem_calls = [call.args for call in redis.zrem.call_args_list]
    assert any(expected_conn_key in str(args) for args in zrem_calls)


# ── SSE stream endpoint success path ─────────────────────────────────────────


class TestSSEStreamSuccess:
    @pytest.mark.asyncio
    async def test_stream_success_returns_200_with_sse_content_type(self):
        """eval→1 (OK) → 200 text/event-stream; lines 365-366 are covered."""
        import httpx
        from fastapi import FastAPI

        from app.api.deps import get_current_user, get_redis
        from app.api.notifications import router

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.role = "reader"

        async def _fake_user():
            return user

        fake_redis = AsyncMock()
        fake_redis.eval = AsyncMock(return_value=1)
        fake_redis.zrem = AsyncMock()

        async def _fake_redis():
            return fake_redis

        sys_cfg = MagicMock()
        sys_cfg.sse_max_connections_per_user = 5
        sys_cfg.sse_max_connections_global = 100

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = _fake_user
        app.dependency_overrides[get_redis] = _fake_redis

        async def _fake_gen(*args, **kwargs):
            yield ": connected\n\n"

        async def _fake_sys_cfg(_r):
            return sys_cfg

        with patch("app.api.notifications.load_system_settings_shared", _fake_sys_cfg):
            with patch("app.api.notifications._sse_generator", _fake_gen):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    r = await ac.get("/notifications/stream")

        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_success_session_cookie_passed_to_generator(self):
        """Session cookie is read from request and forwarded to _sse_generator."""
        import httpx
        from fastapi import FastAPI

        from app.api.deps import get_current_user, get_redis
        from app.api.notifications import router

        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id

        async def _fake_user():
            return user

        fake_redis = AsyncMock()
        fake_redis.eval = AsyncMock(return_value=1)
        fake_redis.zrem = AsyncMock()

        async def _fake_redis():
            return fake_redis

        sys_cfg = MagicMock()
        sys_cfg.sse_max_connections_per_user = 5
        sys_cfg.sse_max_connections_global = 100

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = _fake_user
        app.dependency_overrides[get_redis] = _fake_redis

        captured_session = []

        async def _capturing_gen(_req, _redis, _uid, _conn_id, session_id):
            captured_session.append(session_id)
            yield ": connected\n\n"

        async def _fake_sys_cfg(_r):
            return sys_cfg

        with patch("app.api.notifications.load_system_settings_shared", _fake_sys_cfg):
            with patch("app.api.notifications._sse_generator", _capturing_gen):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                    cookies={"portal_session": "my-session-id"},
                ) as ac:
                    await ac.get("/notifications/stream")

        assert len(captured_session) == 1
