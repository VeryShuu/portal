from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from dateutil.relativedelta import relativedelta


def make_date(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.utc)


def partition_name(year: int, month: int) -> str:
    return f"audit_log_{year:04d}_{month:02d}"


class TestPartitionNaming:
    def test_partition_name_format_single_digit_month(self):
        assert partition_name(2026, 4) == "audit_log_2026_04"

    def test_partition_name_format_double_digit_month(self):
        assert partition_name(2026, 11) == "audit_log_2026_11"

    def test_partition_name_january(self):
        assert partition_name(2027, 1) == "audit_log_2027_01"

    def test_partition_name_december(self):
        assert partition_name(2026, 12) == "audit_log_2026_12"


class TestEnsurePartitions:
    @pytest.fixture
    def mock_conn(self):
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=False)
        conn.execute = AsyncMock(return_value=None)
        return conn

    @pytest.mark.asyncio
    async def test_creates_partitions_for_months_ahead(self, mock_conn):
        from app.services.audit_partitions import ensure_partitions

        now = datetime(2026, 4, 15, tzinfo=timezone.utc)
        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            created = await ensure_partitions(mock_conn, months_ahead=2)

        assert len(created) == 3
        assert "audit_log_2026_04" in created
        assert "audit_log_2026_05" in created
        assert "audit_log_2026_06" in created

    @pytest.mark.asyncio
    async def test_skips_existing_partitions(self, mock_conn):
        from app.services.audit_partitions import ensure_partitions

        mock_conn.fetchval = AsyncMock(side_effect=[True, False, False])

        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            created = await ensure_partitions(mock_conn, months_ahead=2)

        assert "audit_log_2026_04" not in created
        assert len(created) == 2

    @pytest.mark.asyncio
    async def test_creates_correct_date_ranges(self, mock_conn):
        from app.services.audit_partitions import ensure_partitions

        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        execute_calls = []

        async def capture_execute(sql, *args):
            execute_calls.append((sql, args))

        mock_conn.execute = capture_execute

        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await ensure_partitions(mock_conn, months_ahead=1)

        assert len(execute_calls) == 2

        start_apr = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end_apr   = datetime(2026, 5, 1, tzinfo=timezone.utc)
        start_may = datetime(2026, 5, 1, tzinfo=timezone.utc)
        end_may   = datetime(2026, 6, 1, tzinfo=timezone.utc)

        _, (s1, e1) = execute_calls[0]
        _, (s2, e2) = execute_calls[1]
        assert s1 == start_apr and e1 == end_apr
        assert s2 == start_may and e2 == end_may


class TestDropOldPartitions:
    @pytest.fixture
    def mock_conn(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        return conn

    @pytest.mark.asyncio
    async def test_drops_partitions_older_than_retention(self, mock_conn):
        from app.services.audit_partitions import drop_old_partitions

        mock_conn.fetch = AsyncMock(return_value=[
            {"relname": "audit_log_2025_01"},
            {"relname": "audit_log_2025_03"},
            {"relname": "audit_log_2026_04"},
        ])

        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            dropped = await drop_old_partitions(mock_conn, retention_months=12)

        assert "audit_log_2025_01" in dropped
        assert "audit_log_2025_03" in dropped
        assert "audit_log_2026_04" not in dropped

    @pytest.mark.asyncio
    async def test_skips_non_audit_tables(self, mock_conn):
        from app.services.audit_partitions import drop_old_partitions

        mock_conn.fetch = AsyncMock(return_value=[
            {"relname": "audit_log_2024_01"},
            {"relname": "users"},
            {"relname": "news_invalid_name"},
        ])

        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            dropped = await drop_old_partitions(mock_conn, retention_months=12)

        assert "users" not in dropped
        assert "news_invalid_name" not in dropped
        assert "audit_log_2024_01" in dropped

    @pytest.mark.asyncio
    async def test_nothing_dropped_if_all_within_retention(self, mock_conn):
        from app.services.audit_partitions import drop_old_partitions

        mock_conn.fetch = AsyncMock(return_value=[
            {"relname": "audit_log_2026_03"},
            {"relname": "audit_log_2026_04"},
        ])

        now = datetime(2026, 4, 1, tzinfo=timezone.utc)
        with patch("app.services.audit_partitions.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            dropped = await drop_old_partitions(mock_conn, retention_months=12)

        assert dropped == []
        mock_conn.execute.assert_not_called()
