"""Tests for app/worker/tasks/integration_health.py.

Покрытие:
- probe_integrations: все интеграции up/down/not-configured
- gating: отключённый модуль / пустые настройки → None (skip)
- Redis-запись результатов
- probe никогда не роняет worker (исключения ловятся)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import integration_health as ih


class TestProbeIntegrations:
    @pytest.mark.asyncio
    async def test_all_up_writes_results_to_redis(self):
        """Все 4 интеграции up → результаты пишутся в Redis hash."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert results == {"keycloak": 1, "nextcloud": 1, "smtp": 1, "collabora": 1}
        mock_redis.hset.assert_awaited_once()
        args = mock_redis.hset.call_args
        assert args.kwargs["mapping"] == {
            "keycloak": "1",
            "nextcloud": "1",
            "smtp": "1",
            "collabora": "1",
        }
        mock_redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_down_integration_records_zero(self):
        """Интеграция down → записывается 0 (не None)."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=False)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert results["keycloak"] == 0
        assert results["nextcloud"] == 1

    @pytest.mark.asyncio
    async def test_not_configured_skipped(self):
        """Интеграция not-configured (None) → не попадает в результаты."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        # keycloak и smtp не сконфигурированы → отсутствуют
        assert "keycloak" not in results
        assert "smtp" not in results
        assert results == {"nextcloud": 1, "collabora": 1}

    @pytest.mark.asyncio
    async def test_probe_exception_does_not_crash(self):
        """Исключение в probe → интерпретируется как down (0), не падает."""
        mock_redis = AsyncMock()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        # keycloak упал с исключением → 0 (belt-and-suspenders catch)
        assert results["keycloak"] == 0

    @pytest.mark.asyncio
    async def test_no_redis_does_not_crash(self):
        """ctx без redis → результаты возвращаются, но не пишутся."""
        ctx = {}
        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert len(results) == 4  # вычислены, просто не записаны

    @pytest.mark.asyncio
    async def test_redis_write_error_swallowed(self):
        """Ошибка записи в Redis → не роняет cron."""
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(side_effect=Exception("redis down"))
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)  # no exception

        assert len(results) == 4


class TestProbeKeycloak:
    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self):
        fake_kc = MagicMock(keycloak_url="", keycloak_realm="")
        with patch(
            "app.services.keycloak.settings._get_kc_settings", return_value=fake_kc
        ):
            result = await ih._probe_keycloak()
        assert result is None

    @pytest.mark.asyncio
    async def test_up_returns_true(self):
        fake_kc = MagicMock(keycloak_url="http://kc:8080", keycloak_realm="portal")
        mock_resp = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.keycloak.settings._get_kc_settings", return_value=fake_kc
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ih._probe_keycloak()
        assert result is True

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        fake_kc = MagicMock(keycloak_url="http://kc:8080", keycloak_realm="portal")

        class _BoomClient:
            def __await__(self):
                raise asyncio.TimeoutError()

        with (
            patch(
                "app.services.keycloak.settings._get_kc_settings", return_value=fake_kc
            ),
            patch("httpx.AsyncClient", side_effect=asyncio.TimeoutError),
        ):
            result = await ih._probe_keycloak()
        assert result is False


class TestProbeSmtp:
    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self):
        fake_cfg = MagicMock()
        fake_cfg.host = ""
        with patch(
            "app.services.email_settings.read_email_settings", return_value=fake_cfg
        ):
            result = await ih._probe_smtp()
        assert result is None

    @pytest.mark.asyncio
    async def test_connection_failed_returns_false(self):
        fake_cfg = MagicMock(host="smtp.example.local", port=25)
        with (
            patch(
                "app.services.email_settings.read_email_settings", return_value=fake_cfg
            ),
            patch("asyncio.open_connection", side_effect=ConnectionRefusedError),
        ):
            result = await ih._probe_smtp()
        assert result is False
