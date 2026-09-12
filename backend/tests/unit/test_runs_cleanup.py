"""Unit-тесты очистки истории прогонов (runs_cleanup, ретеншн 7 дней)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.worker.tasks import runs_cleanup as rc


class _FakeSessionCtx:
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def _make_session(rowcounts: list[int]) -> MagicMock:
    session = MagicMock()
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=None)
    begin.__aexit__ = AsyncMock(return_value=False)
    session.begin = begin
    session.execute = AsyncMock(side_effect=[MagicMock(rowcount=n) for n in rowcounts])
    return session


async def test_cleanup_deletes_older_than_7_days_for_all_tables():
    session = _make_session([3, 0, 5])
    with patch.object(rc, "AsyncSessionLocal", lambda: _FakeSessionCtx(session)):
        deleted = await rc.cleanup_module_runs({})

    assert deleted == {
        "erp_sync_runs": 3,
        "erp_absences_runs": 0,
        "directum_runs": 5,
    }
    # Три DELETE по трём таблицам.
    assert session.execute.await_count == 3


async def test_cutoff_is_7_days_back():
    """WHERE-условие строится от «сейчас минус 7 дней» (хардкод-ретеншн)."""
    session = _make_session([0, 0, 0])
    before = datetime.now(UTC) - timedelta(days=7)
    with patch.object(rc, "AsyncSessionLocal", lambda: _FakeSessionCtx(session)):
        await rc.cleanup_module_runs({})
    stmt = session.execute.await_args_list[0].args[0]
    cutoff = stmt.compile(compile_kwargs={"literal_binds": False}).params["started_at_1"]
    assert abs((cutoff - before).total_seconds()) < 5
