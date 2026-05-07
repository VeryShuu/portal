"""Unit tests for bulk file operations (bulk-delete, bulk-move).

Covers:
- _validate_bulk_names: dedup, sanitize, traversal protection
- _try_set_inflight / _clear_inflight: SETNX semantics
- Schema validation: empty / over-limit
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.files import (
    _bulk_inflight_key,
    _clear_inflight,
    _try_set_inflight,
    _validate_bulk_names,
)
from app.core.constants import MAX_BULK_FILES


# ── _validate_bulk_names ─────────────────────────────────────────────────────


def test_validate_bulk_names_happy():
    valid, invalid = _validate_bulk_names(["a.txt", "b.pdf"])
    assert valid == ["a.txt", "b.pdf"]
    assert invalid == []


def test_validate_bulk_names_dedup():
    valid, invalid = _validate_bulk_names(["a.txt", "a.txt", "b.txt"])
    assert valid == ["a.txt", "b.txt"]
    assert invalid == []


def test_validate_bulk_names_invalid_traversal():
    valid, invalid = _validate_bulk_names(["../etc/passwd"])
    # rsplit("/")[-1] -> "passwd" — sanitize ok. Traversal-via-/ defended by basename.
    assert valid == ["passwd"]
    assert invalid == []


def test_validate_bulk_names_invalid_chars():
    valid, invalid = _validate_bulk_names(["a\x00b.txt", "ok.txt"])
    assert valid == ["ok.txt"]
    assert len(invalid) == 1
    assert invalid[0].error == "invalid_name"


def test_validate_bulk_names_dot_only():
    valid, invalid = _validate_bulk_names([".", ".."])
    assert valid == []
    assert len(invalid) == 2
    assert all(i.error == "invalid_name" for i in invalid)


def test_validate_bulk_names_empty_after_strip():
    valid, invalid = _validate_bulk_names(["   "])
    assert valid == []
    assert len(invalid) == 1


# ── _try_set_inflight / _clear_inflight ──────────────────────────────────────


@pytest.mark.asyncio
async def test_try_set_inflight_acquires():
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    user_id = uuid.uuid4()
    assert await _try_set_inflight(redis, user_id) is True
    redis.set.assert_called_once()
    args, kwargs = redis.set.call_args
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") == 60
    assert args[0] == _bulk_inflight_key(user_id)


@pytest.mark.asyncio
async def test_try_set_inflight_busy():
    redis = MagicMock()
    redis.set = AsyncMock(return_value=None)
    assert await _try_set_inflight(redis, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_clear_inflight_swallows_errors():
    redis = MagicMock()
    redis.delete = AsyncMock(side_effect=RuntimeError("boom"))
    # Should not raise.
    await _clear_inflight(redis, uuid.uuid4())


@pytest.mark.asyncio
async def test_clear_inflight_calls_delete():
    redis = MagicMock()
    redis.delete = AsyncMock()
    user_id = uuid.uuid4()
    await _clear_inflight(redis, user_id)
    redis.delete.assert_called_once_with(_bulk_inflight_key(user_id))


# ── Schemas ──────────────────────────────────────────────────────────────────


def test_bulk_delete_request_empty_rejected():
    from pydantic import ValidationError

    from app.schemas.files import BulkDeleteRequest

    with pytest.raises(ValidationError):
        BulkDeleteRequest(filenames=[])


def test_bulk_delete_request_over_limit_rejected():
    from pydantic import ValidationError

    from app.schemas.files import BulkDeleteRequest

    with pytest.raises(ValidationError):
        BulkDeleteRequest(filenames=[f"f{i}.txt" for i in range(MAX_BULK_FILES + 1)])


def test_bulk_delete_request_at_limit_ok():
    from app.schemas.files import BulkDeleteRequest

    req = BulkDeleteRequest(filenames=[f"f{i}.txt" for i in range(MAX_BULK_FILES)])
    assert len(req.filenames) == MAX_BULK_FILES


def test_bulk_move_request_requires_target():
    from pydantic import ValidationError

    from app.schemas.files import BulkMoveRequest

    with pytest.raises(ValidationError):
        BulkMoveRequest(filenames=["a.txt"])  # type: ignore[call-arg]


def test_bulk_move_request_ok():
    from app.schemas.files import BulkMoveRequest

    req = BulkMoveRequest(filenames=["a.txt"], target_folder_id=uuid.uuid4())
    assert req.filenames == ["a.txt"]
