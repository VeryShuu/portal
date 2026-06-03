"""Unit-тесты для worker/tasks/*.py.

Покрытие:
audit.py:
- _parse_dt: None → now(), str ISO → datetime, datetime → passthrough
- flush_audit_queue: lock занят → возвращает 0
- flush_audit_queue: пустая очередь → 0 вставок
- flush_audit_queue: вставляет записи батчами

metrics.py:
- _dir_size_bytes: несуществующая директория → 0, существующая → суммарный размер
- refresh_custom_metrics: без pool → только Redis-метрики
- refresh_custom_metrics: сохраняет снапшот в Redis
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── _parse_dt ─────────────────────────────────────────────────────────────────


class TestParseDt:
    def test_none_returns_current_time(self):
        from app.worker.tasks.audit import _parse_dt

        before = datetime.now(tz=UTC)
        result = _parse_dt(None)
        after = datetime.now(tz=UTC)
        assert before <= result <= after

    def test_iso_string_parsed(self):
        from app.worker.tasks.audit import _parse_dt

        iso = "2024-06-15T12:00:00+00:00"
        result = _parse_dt(iso)
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_datetime_passed_through(self):
        from app.worker.tasks.audit import _parse_dt

        dt = datetime(2023, 1, 1, tzinfo=UTC)
        result = _parse_dt(dt)
        assert result == dt


# ── flush_audit_queue ─────────────────────────────────────────────────────────


class TestFlushAuditQueue:
    def _make_redis(self, lock_acquired=True, items=None):
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=lock_acquired)
        redis.delete = AsyncMock()
        redis.lrange = AsyncMock(return_value=items or [])
        redis.lmove = AsyncMock(return_value=None)
        redis.llen = AsyncMock(return_value=0)
        return redis

    def _make_pool(self, conn=None):
        if conn is None:
            conn = AsyncMock()
            conn.executemany = AsyncMock()
        pool = AsyncMock()
        pool.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=conn),
                __aexit__=AsyncMock(return_value=None),
            )
        )
        return pool

    async def test_lock_taken_returns_zero(self):
        from app.worker.tasks.audit import flush_audit_queue

        redis = self._make_redis(lock_acquired=False)
        result = await flush_audit_queue({"redis": redis, "pg_pool": self._make_pool()})
        assert result == 0

    async def test_empty_queue_returns_zero(self):
        from app.worker.tasks.audit import flush_audit_queue

        redis = self._make_redis(lock_acquired=True, items=[])
        redis.lmove = AsyncMock(return_value=None)
        result = await flush_audit_queue({"redis": redis, "pg_pool": self._make_pool()})
        assert result == 0

    async def test_inserts_records_from_queue(self):
        from app.worker.tasks.audit import flush_audit_queue

        record = json.dumps(
            {
                "event_type": "news.created",
                "user_id": "u1",
                "user_email": "u@example.com",
                "resource_type": "news",
                "resource_id": "n1",
                "resource_title": "Test",
                "ip_address": "127.0.0.1",
                "user_agent": "test",
                "metadata": {},
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        )

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock()
        call_count = [0]

        async def mock_lrange(key, start, end):
            if call_count[0] == 0:
                call_count[0] += 1
                return [record]
            return []

        redis.lrange = mock_lrange
        redis.lmove = AsyncMock(return_value=None)

        conn = AsyncMock()
        conn.executemany = AsyncMock()
        pool = AsyncMock()
        pool.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=conn),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        result = await flush_audit_queue({"redis": redis, "pg_pool": pool})
        assert result == 1
        conn.executemany.assert_called_once()

    async def test_releases_lock_on_exception(self):
        from app.worker.tasks.audit import flush_audit_queue

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock()
        redis.lrange = AsyncMock(side_effect=RuntimeError("boom"))
        redis.lmove = AsyncMock(return_value=None)

        redis.eval = AsyncMock()

        with pytest.raises(RuntimeError):
            await flush_audit_queue({"redis": redis, "pg_pool": self._make_pool()})

        redis.eval.assert_called()


# ── _dir_size_bytes ───────────────────────────────────────────────────────────


class TestDirSizeBytes:
    def test_missing_dir_returns_zero(self, tmp_path):
        from app.worker.tasks.metrics import _dir_size_bytes

        result = _dir_size_bytes(tmp_path / "nonexistent")
        assert result == 0

    def test_empty_dir_returns_zero(self, tmp_path):
        from app.worker.tasks.metrics import _dir_size_bytes

        empty = tmp_path / "empty"
        empty.mkdir()
        result = _dir_size_bytes(empty)
        assert result == 0

    def test_counts_file_sizes(self, tmp_path):
        from app.worker.tasks.metrics import _dir_size_bytes

        d = tmp_path / "data"
        d.mkdir()
        (d / "a.txt").write_bytes(b"hello")
        (d / "b.txt").write_bytes(b"world!")
        result = _dir_size_bytes(d)
        assert result == 11

    def test_recursive_sum(self, tmp_path):
        from app.worker.tasks.metrics import _dir_size_bytes

        d = tmp_path / "data"
        sub = d / "sub"
        sub.mkdir(parents=True)
        (d / "file1.txt").write_bytes(b"aa")
        (sub / "file2.txt").write_bytes(b"bbb")
        result = _dir_size_bytes(d)
        assert result == 5


# ── refresh_custom_metrics ────────────────────────────────────────────────────


class TestRefreshCustomMetrics:
    async def test_saves_snapshot_to_redis(self, tmp_path):
        from app.worker.tasks import metrics as metrics_mod
        from app.worker.tasks.metrics import refresh_custom_metrics

        redis = AsyncMock()
        redis.llen = AsyncMock(return_value=0)
        redis.scan_iter = MagicMock(return_value=_async_iter([]))
        redis.set = AsyncMock()

        with patch.object(metrics_mod, "PHOTOS_ORIGINALS_DIR", tmp_path / "photos"):
            await refresh_custom_metrics({"redis": redis})

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        assert call_args[0][0] == "metrics:snapshot"
        snapshot = json.loads(call_args[0][1])
        assert "generated_at" in snapshot

    async def test_returns_snapshot_dict(self, tmp_path):
        from app.worker.tasks import metrics as metrics_mod
        from app.worker.tasks.metrics import refresh_custom_metrics

        redis = AsyncMock()
        redis.llen = AsyncMock(return_value=3)
        redis.scan_iter = MagicMock(return_value=_async_iter([]))
        redis.set = AsyncMock()

        with patch.object(metrics_mod, "PHOTOS_ORIGINALS_DIR", tmp_path / "photos"):
            result = await refresh_custom_metrics({"redis": redis})

        assert isinstance(result, dict)
        assert result.get("audit_queue_depth") == 3

    async def test_no_pool_skips_db_metrics(self, tmp_path):
        from app.worker.tasks import metrics as metrics_mod
        from app.worker.tasks.metrics import refresh_custom_metrics

        redis = AsyncMock()
        redis.llen = AsyncMock(return_value=0)
        redis.scan_iter = MagicMock(return_value=_async_iter([]))
        redis.set = AsyncMock()

        with patch.object(metrics_mod, "PHOTOS_ORIGINALS_DIR", tmp_path / "photos"):
            result = await refresh_custom_metrics({"redis": redis})

        assert "users_total" not in result
        assert "kb_articles_total" not in result

    async def test_photo_storage_calculated(self, tmp_path):
        from app.worker.tasks import metrics as metrics_mod
        from app.worker.tasks.metrics import refresh_custom_metrics

        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        (photos_dir / "img.jpg").write_bytes(b"x" * 1024)

        redis = AsyncMock()
        redis.llen = AsyncMock(return_value=0)
        redis.scan_iter = MagicMock(return_value=_async_iter([]))
        redis.set = AsyncMock()

        with patch.object(metrics_mod, "PHOTOS_ORIGINALS_DIR", photos_dir):
            result = await refresh_custom_metrics({"redis": redis})

        assert result.get("photo_storage_bytes") == 1024


def _async_iter(items):
    async def _gen():
        for item in items:
            yield item

    return _gen()
