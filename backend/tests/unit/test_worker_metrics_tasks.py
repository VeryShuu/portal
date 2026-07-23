"""Tests for app/worker/tasks/metrics.py.

Покрытие:
- _dir_size_bytes: path doesn't exist / normal files / OSError on rglob / OSError on stat
- refresh_custom_metrics: audit queue / SSE / DB gauges (pool is None / pool available) /
  photo storage / snapshot persist / exception swallowing
- worker_heartbeat: sets key in Redis
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import metrics as metrics_task


class TestDirSizeBytes:
    def test_missing_path_returns_zero(self, tmp_path):
        missing = tmp_path / "nonexistent"
        assert metrics_task._dir_size_bytes(missing) == 0

    def test_empty_dir_returns_zero(self, tmp_path):
        assert metrics_task._dir_size_bytes(tmp_path) == 0

    def test_sums_file_sizes(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"hello")
        (tmp_path / "b.txt").write_bytes(b"world!")
        result = metrics_task._dir_size_bytes(tmp_path)
        assert result == 11

    def test_nested_files(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "x.bin").write_bytes(b"x" * 100)
        result = metrics_task._dir_size_bytes(tmp_path)
        assert result == 100

    def test_oserror_on_stat_skipped(self, tmp_path):
        (tmp_path / "ok.txt").write_bytes(b"abc")

        original_rglob = Path.rglob

        def _mock_rglob(self, pattern):
            for entry in original_rglob(self, pattern):
                if entry.name == "ok.txt":
                    bad = MagicMock(spec=Path)
                    bad.is_file.return_value = True
                    bad.stat.side_effect = OSError("permission denied")
                    yield bad
                else:
                    yield entry

        with patch.object(Path, "rglob", _mock_rglob):
            result = metrics_task._dir_size_bytes(tmp_path)

        assert result == 0

    def test_oserror_on_rglob_returns_partial(self, tmp_path):
        def _bad_rglob(self, pattern):
            raise OSError("no permission")

        with patch.object(Path, "rglob", _bad_rglob):
            result = metrics_task._dir_size_bytes(tmp_path)

        assert result == 0


class TestRefreshCustomMetrics:
    @pytest.mark.asyncio
    async def test_returns_snapshot_with_audit_and_sse(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=5)
        mock_redis.zcard = AsyncMock(return_value=3)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=b"1700000000")
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent_path")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert result["audit_queue_depth"] == 5
        assert result["audit_processing_depth"] == 5
        assert result["sse_connections"] == 3
        assert result["worker_heartbeat_ts"] == 1_700_000_000
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_worker_heartbeat_absent_omitted(self):
        """Нет mtime-ключа (воркер ещё не стартовал / TTL истёк) → поле
        отсутствует в snapshot. Gauge не гидрируется, PortalWorkerDown ловит."""
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "worker_heartbeat_ts" not in result

    @pytest.mark.asyncio
    async def test_worker_heartbeat_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "worker_heartbeat_ts" not in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_audit_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "audit_queue_depth" not in result

    @pytest.mark.asyncio
    async def test_sse_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(side_effect=Exception("sse scan failed"))
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "sse_connections" not in result

    @pytest.mark.asyncio
    async def test_db_gauges_populated_when_pool_available(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        mock_row = {
            "u_kc": 10,
            "u_local": 2,
            "kb_pub": 5,
            "kb_draft": 1,
            "news_pub": 3,
            "news_draft": 2,
            "active_1h": 7,
        }
        mock_outbox = {
            "e_pending": 4,
            "e_dlq": 1,
            "e_stale": 0,
            "m_pending": 2,
            "m_dlq": 0,
            "m_stale": 0,
        }

        mock_conn = AsyncMock()
        # Два последовательных fetchrow: основной бизнес-запрос + outbox-запрос.
        mock_conn.fetchrow = AsyncMock(side_effect=[mock_row, mock_outbox])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = {"redis": mock_redis, "pg_pool": mock_pool}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert result["users_total"]["keycloak"] == 10
        assert result["users_total"]["local"] == 2
        assert result["kb_articles_total"]["published"] == 5
        assert result["news_published_total"]["published"] == 3
        assert result["active_users_1h"] == 7
        assert result["email_outbox"] == {"pending": 4, "dlq": 1, "sending_stale": 0}
        assert result["messenger_outbox"] == {"pending": 2, "dlq": 0, "sending_stale": 0}

    @pytest.mark.asyncio
    async def test_db_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=Exception("db down"))
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = {"redis": mock_redis, "pg_pool": mock_pool}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "users_total" not in result

    @pytest.mark.asyncio
    async def test_photo_storage_size_populated(self, tmp_path):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        (tmp_path / "photo.jpg").write_bytes(b"x" * 512)
        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", tmp_path):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert result.get("photo_storage_bytes") == 512

    @pytest.mark.asyncio
    async def test_snapshot_persist_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(side_effect=Exception("redis write error"))

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_no_pool_skips_db_gauges(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=2)
        mock_redis.zcard = AsyncMock(return_value=1)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert "users_total" not in result


class TestWorkerHeartbeat:
    @pytest.mark.asyncio
    async def test_sets_heartbeat_and_mtime_keys(self):
        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.set = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=pipe)

        ctx = {"redis": mock_redis}
        with patch.object(metrics_task.time, "time", return_value=1_700_000_000):
            await metrics_task.worker_heartbeat(ctx)

        # Pipeline пишет ДВА ключа: TTL-key (для docker healthcheck) + mtime.
        pipe.set.assert_any_call(
            metrics_task.WORKER_HEARTBEAT_KEY,
            "1",
            ex=metrics_task.WORKER_HEARTBEAT_TTL,
        )
        pipe.set.assert_any_call(
            metrics_task.WORKER_HEARTBEAT_MTIME_KEY,
            "1700000000",
            ex=metrics_task.WORKER_HEARTBEAT_TTL,
        )
        pipe.execute.assert_awaited_once()


class TestArqJobsSnapshot:
    """refresh_custom_metrics должен подхватывать ARQ-хэши в snapshot."""

    @pytest.mark.asyncio
    async def test_arq_jobs_included_in_snapshot(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.hgetall = AsyncMock(
            side_effect=[
                {b"test:succeeded": 5, b"test:failed": 1},  # arq:metrics:jobs
                {b"test:count": 6, b"test:sum": 12345},  # arq:metrics:job_ms
            ]
        )

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        assert result["arq_jobs"] == {"test:succeeded": 5, "test:failed": 1}
        assert result["arq_job_ms"] == {"test:count": 6, "test:sum": 12345}

    @pytest.mark.asyncio
    async def test_arq_jobs_error_swallowed(self):
        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.hgetall = AsyncMock(side_effect=Exception("redis down"))

        ctx = {"redis": mock_redis}

        with patch.object(metrics_task, "PHOTOS_ORIGINALS_DIR", Path("/nonexistent")):
            result = await metrics_task.refresh_custom_metrics(ctx)

        # ARQ-блок падает, но snapshot всё равно публикуется
        assert "arq_jobs" not in result
        assert "generated_at" in result


class TestTrackArqJob:
    """Декоратор track_arq_job: счётчики started/succeeded/failed + duration."""

    @pytest.mark.asyncio
    async def test_success_records_started_and_succeeded(self):
        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.hincrby = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=pipe)

        @metrics_task.track_arq_job
        async def my_task(ctx):
            return "ok"

        result = await my_task({"redis": mock_redis})
        assert result == "ok"

        # started (отдельный hincrby до вызова) + терминальный succeeded (в pipeline)
        mock_redis.hincrby.assert_awaited_once_with(
            metrics_task.ARQ_JOBS_KEY, "my_task:started", 1
        )
        pipe.hincrby.assert_any_call(metrics_task.ARQ_JOBS_KEY, "my_task:succeeded", 1)
        pipe.hincrby.assert_any_call(metrics_task.ARQ_JOB_TIME_KEY, "my_task:count", 1)

    @pytest.mark.asyncio
    async def test_failure_records_failed_and_reraises(self):
        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.hincrby = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=pipe)

        @metrics_task.track_arq_job
        async def bad_task(ctx):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await bad_task({"redis": mock_redis})

        mock_redis.hincrby.assert_awaited_once_with(
            metrics_task.ARQ_JOBS_KEY, "bad_task:started", 1
        )
        pipe.hincrby.assert_any_call(metrics_task.ARQ_JOBS_KEY, "bad_task:failed", 1)

    @pytest.mark.asyncio
    async def test_no_redis_does_not_break(self):
        @metrics_task.track_arq_job
        async def my_task(ctx):
            return "ok"

        # ctx без redis — декоратор не падает, функция выполняется
        result = await my_task({})
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_redis_write_error_does_not_break_job(self):
        mock_redis = AsyncMock()
        mock_redis.hincrby = AsyncMock(side_effect=Exception("redis down"))

        @metrics_task.track_arq_job
        async def my_task(ctx):
            return "ok"

        result = await my_task({"redis": mock_redis})
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        @metrics_task.track_arq_job
        async def do_something_specific(ctx):
            return None

        assert do_something_specific.__name__ == "do_something_specific"
