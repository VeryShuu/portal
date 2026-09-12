"""Tests for app/worker/tasks/synthetic_probe.py.

Покрытие:
- run_synthetic_probe: ok/failed → запись в Redis
- not-configured (screenshot-service вернул configured=False) → skip
- screenshot-service unreachable → graceful failure
- Redis write error swallowed
- portal_base_url читается из SystemSettings и передаётся в payload /probe
  (нужен для spoof-Origin, иначе login падает на CSRF Origin-check)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import synthetic_probe as sp

_PORTAL_BASE_URL = "https://portal-test.example.com"


def _mock_client(resp_json: dict | None = None, *, exc: Exception | None = None) -> AsyncMock:
    """Build a mock httpx.AsyncClient that either returns resp_json or raises exc."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = resp_json or {}
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=exc if exc is not None else None,
        return_value=None if exc is not None else mock_resp,
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.fixture(autouse=True)
def _stub_system_settings():
    """portal_base_url должен читаться из SystemSettings; в unit-окружении
    файла /data/settings/system.json нет — стабим на тестовое значение."""
    fake_settings = MagicMock()
    fake_settings.portal_base_url = _PORTAL_BASE_URL
    with patch(
        "app.core.system_config.load_system_settings",
        return_value=fake_settings,
    ):
        yield


class TestRunSyntheticProbe:
    @pytest.mark.asyncio
    async def test_ok_returns_executor_result(self):
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
        mock_redis.hset.assert_not_awaited()
        # portal_base_url передаётся в payload /probe (для spoof-Origin)
        sent_json = mock_client.post.call_args.kwargs["json"]
        assert sent_json["portal_base_url"] == _PORTAL_BASE_URL

    @pytest.mark.asyncio
    async def test_failed_flow_returns_executor_result(self):
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
        assert result["step_failed"] == "login_status_401"
        mock_redis.hset.assert_not_awaited()

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
    async def test_service_unreachable_is_unavailable(self):
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
        assert result["configured"] is None
        assert result["step_failed"] == "service_unavailable"
        mock_redis.hset.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            {"ok": True, "flow": "login_and_load"},
            {"ok": True, "configured": True, "flow": "unexpected"},
        ],
    )
    async def test_invalid_executor_response_is_unavailable(self, payload):
        mock_client = _mock_client(payload)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await sp.run_synthetic_probe({})

        assert result["ok"] is False
        assert result["configured"] is None
        assert result["step_failed"] == "service_unavailable"

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

    @pytest.mark.asyncio
    async def test_portal_base_url_failure_falls_back_to_empty(self):
        """load_system_settings упал → portal_base_url="" , но cron не ломается.

        Пустой portal_base_url деградирует пробу (login→403 CSRF), но запрос к
        /probe всё равно уходит — не должно валить весь cron-цикл.
        """
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "ok": False,
            "configured": True,
            "flow": "login_and_load",
            "elapsed_ms": 100,
            "step_failed": "login_status_403",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # Перекрываем autouse-стаб: эмулируем сбой чтения SystemSettings.
        with (
            patch(
                "app.core.system_config.load_system_settings",
                side_effect=RuntimeError("settings file unreadable"),
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await sp.run_synthetic_probe({"redis": AsyncMock()})

        assert result["ok"] is False  # деградировало, но не упало
        sent_json = mock_client.post.call_args.kwargs["json"]
        assert sent_json["portal_base_url"] == ""  # пустой fallback
