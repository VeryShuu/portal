"""Unit: cron-обёртка ретеншена одноразовых кодов входа (learning).

БД мокается — проверяется каркас (условие удаления: used/expired + cutoff,
commit, возвращаемый rowcount); SQL-семантика покрыта интеграционным
стеком test-integration.sh при необходимости."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import learning_cleanup

pytestmark = pytest.mark.asyncio


def _session_ctx(rowcount: int) -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    result = MagicMock()
    result.rowcount = rowcount
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock(return_value=None)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock()
    factory.return_value = ctx
    return factory, session


async def test_cleanup_deletes_and_commits():
    factory, session = _session_ctx(7)
    with patch.object(learning_cleanup, "AsyncSessionLocal", factory):
        deleted = await learning_cleanup.cleanup_expired_resets({})
    assert deleted == 7
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
    # в statement уходит DELETE по learning_login_codes
    stmt = session.execute.await_args.args[0]
    assert "learning_login_codes" in str(stmt)


async def test_cleanup_zero_rowcount_ok():
    factory, session = _session_ctx(0)
    with patch.object(learning_cleanup, "AsyncSessionLocal", factory):
        deleted = await learning_cleanup.cleanup_expired_resets({})
    assert deleted == 0
    session.commit.assert_awaited_once()
