"""Unit-тесты: Redis session store."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.session import (
    SESSION_KEY_PREFIX,
    PKCE_KEY_PREFIX,
    SESSION_TTL,
    PKCE_TTL,
    delete_pkce_state,
    delete_session,
    get_pkce_state,
    get_session,
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
