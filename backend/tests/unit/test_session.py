"""Unit-тесты: Redis session store."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.session import (
    PKCE_KEY_PREFIX,
    PKCE_TTL,
    SESSION_KEY_PREFIX,
    SESSION_TTL,
    _USER_SESSIONS_KEY_PREFIX,
    delete_pkce_state,
    delete_session,
    extend_session,
    get_and_delete_pkce_state,
    get_pkce_state,
    get_session,
    get_session_from_request,
    invalidate_all_user_sessions,
    save_pkce_state,
    save_session,
)


@pytest.fixture
def redis():
    r = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_save_and_get_session(redis):
    data = {"access_token": "tok", "user_id": "uid-1"}
    sid = "test-session-id"

    redis.setex = AsyncMock()
    raw = json.dumps(data)
    redis.get = AsyncMock(return_value=raw)

    await save_session(redis, sid, data)
    redis.setex.assert_called_once_with(f"{SESSION_KEY_PREFIX}{sid}", SESSION_TTL, raw)

    result = await get_session(redis, sid)
    assert result == data


@pytest.mark.asyncio
async def test_get_session_missing(redis):
    redis.get = AsyncMock(return_value=None)
    result = await get_session(redis, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_session(redis):
    redis.delete = AsyncMock()
    await delete_session(redis, "sid")
    redis.delete.assert_called_once_with(f"{SESSION_KEY_PREFIX}sid")


@pytest.mark.asyncio
async def test_save_pkce_state(redis):
    redis.setex = AsyncMock()
    await save_pkce_state(redis, "state1", "verifier1", "nonce1", "/dashboard")
    assert redis.setex.called
    call_args = redis.setex.call_args
    key, ttl, value = call_args[0]
    assert key == f"{PKCE_KEY_PREFIX}state1"
    assert ttl == PKCE_TTL
    stored = json.loads(value)
    assert stored["verifier"] == "verifier1"
    assert stored["nonce"] == "nonce1"
    assert stored["redirect_after"] == "/dashboard"


@pytest.mark.asyncio
async def test_get_pkce_state_missing(redis):
    redis.get = AsyncMock(return_value=None)
    result = await get_pkce_state(redis, "unknown_state")
    assert result is None


@pytest.mark.asyncio
async def test_delete_pkce_state(redis):
    redis.delete = AsyncMock()
    await delete_pkce_state(redis, "state_x")
    redis.delete.assert_called_once_with(f"{PKCE_KEY_PREFIX}state_x")


@pytest.mark.asyncio
async def test_save_session_without_user_id(redis):
    data = {"access_token": "tok"}
    sid = "no-user-id-session"
    redis.setex = AsyncMock()

    await save_session(redis, sid, data)
    redis.setex.assert_called_once()
    redis.sadd.assert_not_called()


@pytest.mark.asyncio
async def test_delete_session_when_no_raw(redis):
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()

    await delete_session(redis, "nonexistent-sid")
    redis.delete.assert_called_once_with(f"{SESSION_KEY_PREFIX}nonexistent-sid")


@pytest.mark.asyncio
async def test_delete_session_raw_without_user_id(redis):
    data = {"access_token": "tok"}
    redis.get = AsyncMock(return_value=json.dumps(data))
    redis.delete = AsyncMock()

    await delete_session(redis, "sid-no-uid")
    redis.srem.assert_not_called()
    redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_extend_session(redis):
    redis.expire = AsyncMock()
    await extend_session(redis, "sid-ext")
    redis.expire.assert_called_once_with(f"{SESSION_KEY_PREFIX}sid-ext", SESSION_TTL)


@pytest.mark.asyncio
async def test_get_pkce_state_found(redis):
    state_data = {"verifier": "v", "nonce": "n", "redirect_after": "/"}
    redis.get = AsyncMock(return_value=json.dumps(state_data))
    result = await get_pkce_state(redis, "state-ok")
    assert result == state_data


@pytest.mark.asyncio
async def test_get_and_delete_pkce_state_found(redis):
    state_data = {"verifier": "v", "nonce": "n", "redirect_after": "/"}
    redis.getdel = AsyncMock(return_value=json.dumps(state_data))
    result = await get_and_delete_pkce_state(redis, "state-ok")
    assert result == state_data


@pytest.mark.asyncio
async def test_get_and_delete_pkce_state_missing(redis):
    redis.getdel = AsyncMock(return_value=None)
    result = await get_and_delete_pkce_state(redis, "no-state")
    assert result is None


@pytest.mark.asyncio
async def test_invalidate_all_user_sessions_no_except(redis):
    redis.smembers = AsyncMock(return_value={"sid1", "sid2"})
    redis.delete = AsyncMock()

    count = await invalidate_all_user_sessions(redis, "user-123")
    assert count == 2
    assert redis.delete.call_count == 3


@pytest.mark.asyncio
async def test_invalidate_all_user_sessions_with_except(redis):
    redis.smembers = AsyncMock(return_value={"sid1", "sid2"})
    redis.delete = AsyncMock()
    redis.srem = AsyncMock()

    count = await invalidate_all_user_sessions(redis, "user-123", except_session_id="sid1")
    assert count == 1
    redis.srem.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_all_user_sessions_empty(redis):
    redis.smembers = AsyncMock(return_value=set())
    redis.delete = AsyncMock()
    redis.srem = AsyncMock()

    count = await invalidate_all_user_sessions(redis, "user-123")
    assert count == 0


@pytest.mark.asyncio
async def test_get_session_from_request_with_cookie(redis):
    from app.core.security import SESSION_COOKIE_NAME

    data = {"user_id": "u1", "access_token": "at"}
    redis.get = AsyncMock(return_value=json.dumps(data))

    request = MagicMock()
    request.cookies = {SESSION_COOKIE_NAME: "sid-cookie"}

    result = await get_session_from_request(request, redis)
    assert result == data


@pytest.mark.asyncio
async def test_get_session_from_request_no_cookie(redis):
    request = MagicMock()
    request.cookies = {}

    result = await get_session_from_request(request, redis)
    assert result is None
