"""T7: тесты для services/audit — push_audit_event и audit.log."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audit import AUDIT_QUEUE_KEY, make_audit_emitter, push_audit_event
from app.services.audit import log as audit_log


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
# audit.log() — прямой INSERT в БД (isolated session)
# ---------------------------------------------------------------------------


def _make_audit_session(execute_side_effect=None, commit_side_effect=None):
    """Return a MagicMock session that works as an async context manager."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_side_effect)
    session.commit = AsyncMock(side_effect=commit_side_effect)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_audit_log_inserts_record() -> None:
    session = _make_audit_session()
    with patch("app.services.audit.AsyncSessionLocal", return_value=session):
        await audit_log(user_id="u-1", event_type="news.created", metadata={"key": "val"})

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()

    call_kwargs = session.execute.await_args.args[1]
    assert call_kwargs["event_type"] == "news.created"
    assert call_kwargs["user_id"] == "u-1"
    assert json.loads(call_kwargs["metadata"]) == {"key": "val"}
    assert call_kwargs["created_at"] is not None


@pytest.mark.asyncio
async def test_audit_log_db_param_ignored_but_accepted() -> None:
    """db= kwarg is kept for API compat but no longer used."""
    session = _make_audit_session()
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.audit.AsyncSessionLocal", return_value=session):
        await audit_log(db=db, event_type="auth.login")

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_log_default_metadata_is_empty_dict() -> None:
    session = _make_audit_session()
    with patch("app.services.audit.AsyncSessionLocal", return_value=session):
        await audit_log(event_type="auth.login")

    call_kwargs = session.execute.await_args.args[1]
    assert json.loads(call_kwargs["metadata"]) == {}
    assert call_kwargs["user_id"] is None


@pytest.mark.asyncio
async def test_audit_log_swallows_db_errors() -> None:
    session = _make_audit_session(execute_side_effect=RuntimeError("db failure"))
    with patch("app.services.audit.AsyncSessionLocal", return_value=session):
        await audit_log(event_type="search")

    session.execute.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_log_swallows_commit_errors() -> None:
    session = _make_audit_session(commit_side_effect=Exception("commit failed"))
    with patch("app.services.audit.AsyncSessionLocal", return_value=session):
        await audit_log(event_type="news.deleted", user_id="u-2")

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_log_uses_isolated_session() -> None:
    """audit.log must not share the caller's session — uses AsyncSessionLocal."""
    sessions_created = []

    def _factory():
        s = _make_audit_session()
        sessions_created.append(s)
        return s

    with patch("app.services.audit.AsyncSessionLocal", side_effect=_factory):
        await audit_log(event_type="test.event")

    assert len(sessions_created) == 1


# ---------------------------------------------------------------------------
# make_audit_emitter() — resource_type-bound thin wrapper over push_audit_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_audit_emitter_binds_resource_type_and_forwards() -> None:
    redis = MagicMock()
    emit = make_audit_emitter("link")

    with patch("app.services.audit.push_audit_event", new_callable=AsyncMock) as mock_push:
        await emit(
            redis,
            event_type="links.created",
            user_id="admin-1",
            resource_id="link-1",
            metadata={"name": "X"},
        )

    mock_push.assert_awaited_once_with(
        redis,
        resource_type="link",
        event_type="links.created",
        user_id="admin-1",
        resource_id="link-1",
        metadata={"name": "X"},
    )


@pytest.mark.asyncio
async def test_make_audit_emitter_resolves_push_at_call_time() -> None:
    """Emitter must look up push_audit_event dynamically so tests can patch it."""
    redis = MagicMock()
    redis.rpush = AsyncMock()
    emit = make_audit_emitter("user")

    await emit(redis, event_type="user.created", user_id="u-1", resource_id="u-2")

    redis.rpush.assert_awaited_once()
    record = json.loads(redis.rpush.await_args.args[1])
    assert record["event_type"] == "user.created"
    assert record["resource_type"] == "user"
    assert record["resource_id"] == "u-2"
    assert record["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_make_audit_emitter_independent_resource_types() -> None:
    redis = MagicMock()
    emit_link = make_audit_emitter("link")
    emit_user = make_audit_emitter("user")

    with patch("app.services.audit.push_audit_event", new_callable=AsyncMock) as mock_push:
        await emit_link(redis, event_type="links.deleted", user_id="a", resource_id="l")
        await emit_user(redis, event_type="user.deleted", user_id="a", resource_id="u")

    assert mock_push.await_args_list[0].kwargs["resource_type"] == "link"
    assert mock_push.await_args_list[1].kwargs["resource_type"] == "user"
