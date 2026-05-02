"""T7: тесты для services/audit — push_audit_event и audit.log."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audit import AUDIT_QUEUE_KEY, log as audit_log, push_audit_event


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


# ---------------------------------------------------------------------------
# audit.log() — прямой INSERT в БД
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_inserts_record() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await audit_log(db=db, user_id="u-1", event_type="news.created", metadata={"key": "val"})

    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()

    call_kwargs = db.execute.await_args.args[1]
    assert call_kwargs["event_type"] == "news.created"
    assert call_kwargs["user_id"] == "u-1"
    assert json.loads(call_kwargs["metadata"]) == {"key": "val"}
    assert call_kwargs["created_at"] is not None


@pytest.mark.asyncio
async def test_audit_log_default_metadata_is_empty_dict() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    await audit_log(db=db, event_type="auth.login")

    call_kwargs = db.execute.await_args.args[1]
    assert json.loads(call_kwargs["metadata"]) == {}
    assert call_kwargs["user_id"] is None


@pytest.mark.asyncio
async def test_audit_log_swallows_db_errors() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db failure"))
    db.commit = AsyncMock()

    await audit_log(db=db, event_type="search")

    db.execute.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_log_swallows_commit_errors() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock(side_effect=Exception("commit failed"))

    await audit_log(db=db, event_type="news.deleted", user_id="u-2")

    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
