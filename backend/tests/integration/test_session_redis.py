"""Integration: сессии и PKCE в реальном Redis."""

from __future__ import annotations

import pytest

from app.services.session import (
    delete_pkce_state,
    delete_session,
    extend_session,
    get_pkce_state,
    get_session,
    save_pkce_state,
    save_session,
)


pytestmark = pytest.mark.asyncio


async def test_save_and_get_session_roundtrip(redis_client):
    await save_session(
        redis_client,
        "sess-1",
        {"user_id": "abc", "auth_source": "local"},
    )
    data = await get_session(redis_client, "sess-1")
    assert data == {"user_id": "abc", "auth_source": "local"}


async def test_delete_session_removes_key(redis_client):
    await save_session(redis_client, "sess-2", {"x": 1})
    await delete_session(redis_client, "sess-2")
    assert await get_session(redis_client, "sess-2") is None


async def test_session_ttl_set(redis_client):
    await save_session(redis_client, "sess-3", {"y": 2})
    ttl = await redis_client.ttl("session:sess-3")
    assert 0 < ttl <= 8 * 3600


async def test_extend_session_resets_ttl(redis_client):
    await save_session(redis_client, "sess-4", {"x": 1})
    await redis_client.expire("session:sess-4", 60)
    await extend_session(redis_client, "sess-4")
    ttl = await redis_client.ttl("session:sess-4")
    assert ttl > 60


async def test_pkce_state_roundtrip(redis_client):
    await save_pkce_state(
        redis_client,
        state="state-1",
        verifier="verifier-1",
        nonce="nonce-1",
        redirect_after="/news",
    )
    data = await get_pkce_state(redis_client, "state-1")
    assert data["verifier"] == "verifier-1"
    assert data["nonce"] == "nonce-1"
    assert data["redirect_after"] == "/news"


async def test_pkce_state_ttl_short(redis_client):
    await save_pkce_state(redis_client, "state-2", "v", "n")
    ttl = await redis_client.ttl("pkce:state-2")
    assert 0 < ttl <= 600


async def test_pkce_delete(redis_client):
    await save_pkce_state(redis_client, "state-3", "v", "n")
    await delete_pkce_state(redis_client, "state-3")
    assert await get_pkce_state(redis_client, "state-3") is None
