"""T7: тесты для services/audit.push_audit_event."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.audit import AUDIT_QUEUE_KEY, push_audit_event


@pytest.mark.asyncio
async def test_push_audit_event_writes_full_payload():
    redis = MagicMock()
    redis.rpush = AsyncMock()

    await push_audit_event(
        redis,
        event_type="news.created",
        user_id="user-1",
        user_email="u@test.local",
        resource_type="news",
        resource_id="news-1",
        resource_title="Hello",
        ip_address="10.0.0.1",
        user_agent="UA/1.0",
        metadata={"source": "api"},
    )

    redis.rpush.assert_awaited_once()
    args = redis.rpush.await_args.args
    assert args[0] == AUDIT_QUEUE_KEY
    record = json.loads(args[1])
    assert record["event_type"] == "news.created"
    assert record["user_id"] == "user-1"
    assert record["user_email"] == "u@test.local"
    assert record["resource_type"] == "news"
    assert record["resource_id"] == "news-1"
    assert record["resource_title"] == "Hello"
    assert record["ip_address"] == "10.0.0.1"
    assert record["user_agent"] == "UA/1.0"
    assert record["metadata"] == {"source": "api"}
    assert record.get("created_at")


@pytest.mark.asyncio
async def test_push_audit_event_default_metadata_is_empty_dict():
    redis = MagicMock()
    redis.rpush = AsyncMock()

    await push_audit_event(redis, event_type="auth.login", user_id="u")

    record = json.loads(redis.rpush.await_args.args[1])
    assert record["metadata"] == {}
    assert record["resource_type"] is None
    assert record["resource_id"] is None
    assert record["user_email"] is None


@pytest.mark.asyncio
async def test_push_audit_event_swallows_redis_errors():
    """Аудит должен fire-and-forget: ошибки Redis НЕ должны падать в обработчик."""
    redis = MagicMock()
    redis.rpush = AsyncMock(side_effect=ConnectionError("redis down"))

    # Не должно поднять исключение
    await push_audit_event(redis, event_type="news.created", user_id="u")
    redis.rpush.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_audit_event_minimal_args():
    redis = MagicMock()
    redis.rpush = AsyncMock()

    await push_audit_event(redis, event_type="search")

    record = json.loads(redis.rpush.await_args.args[1])
    assert record["event_type"] == "search"
    assert record["user_id"] is None


@pytest.mark.asyncio
async def test_push_audit_event_serialises_complex_metadata():
    redis = MagicMock()
    redis.rpush = AsyncMock()

    meta = {"old_role": "reader", "new_role": "editor", "ids": [1, 2, 3]}
    await push_audit_event(
        redis,
        event_type="admin.role_changed",
        user_id="admin-1",
        metadata=meta,
    )

    record = json.loads(redis.rpush.await_args.args[1])
    assert record["metadata"] == meta
