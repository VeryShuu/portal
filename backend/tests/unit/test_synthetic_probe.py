"""Tests for app/worker/tasks/synthetic_probe.py.

Покрытие:
- run_synthetic_probe: ok/failed → запись в Redis
- not-configured (screenshot-service вернул configured=False) → skip
- screenshot-service unreachable → graceful failure
- Redis write error swallowed
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import synthetic_probe as sp


class TestRunSyntheticProbe:
    @pytest.mark.asyncio
    async def test_ok_writes_result_to_redis(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": True,
            "configured": True,
            "flow": "login_and_load",
            "elapsed_ms": 4500,
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)

        assert result["ok"] is True
        mock_redis.hset.assert_awaited_once()
        mapping = mock_redis.hset.call_args.kwargs["mapping"]
        assert mapping == {"login_and_load:ok": "1", "login_and_load:ms": "4500"}
        mock_redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_records_zero(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": False,
            "configured": True,
            "flow": "login_and_load",
            "elapsed_ms": 12000,
            "step_failed": "login_status_401",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)

        assert result["ok"] is False
        mapping = mock_redis.hset.call_args.kwargs["mapping"]
        assert mapping["login_and_load:ok"] == "0"

    @pytest.mark.asyncio
    async def test_not_configured_skips_redis_write(self):
        """configured=False → probe skip, nothing written to Redis."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": False,
            "configured": False,
            "flow": "login_and_load",
            "error": "PROBE_ADMIN_EMAIL/PASSWORD not set",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)

        assert result is None
        mock_redis.hset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_service_unreachable_records_failure(self):
        """screenshot-service недоступен → graceful failure (ok=0)."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)

        assert result["ok"] is False
        assert result["step_failed"] == "service_unreachable"
        mock_redis.hset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_write_error_swallowed(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": True,
            "configured": True,
            "flow": "login_and_load",
            "elapsed_ms": 1000,
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(side_effect=Exception("redis down"))
        ctx = {"redis": mock_redis}

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)  # no exception

        assert result["ok"] is True  # результат возвращается несмотря на ошибку записи

    @pytest.mark.asyncio
    async def test_no_redis_still_returns_result(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": True,
            "configured": True,
            "flow": "login_and_load",
            "elapsed_ms": 500,
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        ctx = {}  # без redis

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe(ctx)

        assert result["ok"] is True
