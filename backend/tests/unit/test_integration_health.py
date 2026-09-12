"""Tests for app/worker/tasks/integration_health.py.

Покрытие:
- probe_integrations: все интеграции up/down/not-configured
- gating: отключённый модуль / пустые настройки → None (skip)
- Redis-запись результатов
- probe никогда не роняет worker (исключения ловятся)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import integration_health as ih

# NB: все probes-тесты ниже патчат и пятый зонд (_probe_erp_approvals) вместе
# с четырьмя классическими — словари результатов не должны зависеть от
# modules.json/БД окружения тестов.


def _mock_pipeline_redis() -> tuple[AsyncMock, MagicMock]:
    redis = AsyncMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    return redis, pipe


class TestProbeIntegrations:
    @pytest.mark.asyncio
    async def test_all_up_writes_results_to_redis(self):
        """Все 5 покрытых здесь интеграций up → результаты пишутся в Redis hash."""
        mock_redis, pipeline = _mock_pipeline_redis()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert results == {
            "keycloak": 1,
            "nextcloud": 1,
            "smtp": 1,
            "collabora": 1,
            "erp_approvals": 1,
        }
        pipeline.delete.assert_any_call(ih.INTEGRATION_HEALTH_KEY)
        pipeline.delete.assert_any_call(ih.INTEGRATION_PROBE_STATE_KEY)
        health_call = next(
            call
            for call in pipeline.hset.call_args_list
            if call.args == (ih.INTEGRATION_HEALTH_KEY,)
        )
        assert health_call.kwargs["mapping"] == {
            "keycloak": "1",
            "nextcloud": "1",
            "smtp": "1",
            "collabora": "1",
            "erp_approvals": "1",
        }
        state_call = next(
            call
            for call in pipeline.hset.call_args_list
            if call.args == (ih.INTEGRATION_PROBE_STATE_KEY,)
        )
        state = state_call.kwargs["mapping"]
        assert state["keycloak:expected"] == "1"
        assert state["keycloak:result"] == "1"
        assert float(state["keycloak:last_attempt"]) > 0
        assert float(state["keycloak:last_completed"]) >= float(state["keycloak:last_attempt"])
        assert float(state["keycloak:result_expires_at"]) > float(state["keycloak:last_completed"])
        assert mock_redis.hset.await_count == 8
        pipeline.expire.assert_called_once_with(
            ih.INTEGRATION_HEALTH_KEY, ih.INTEGRATION_HEALTH_TTL
        )
        pipeline.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_down_integration_records_zero(self):
        """Интеграция down → записывается 0 (не None)."""
        mock_redis, _pipeline = _mock_pipeline_redis()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=False)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert results["keycloak"] == 0
        assert results["nextcloud"] == 1

    @pytest.mark.asyncio
    async def test_not_configured_skipped(self):
        """Интеграция not-configured (None) → не попадает в результаты."""
        mock_redis, _pipeline = _mock_pipeline_redis()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=None)),
        ):
            results = await ih.probe_integrations(ctx)

        # keycloak и smtp не сконфигурированы → отсутствуют
        assert "keycloak" not in results
        assert "smtp" not in results
        assert "erp_approvals" not in results
        assert results == {"nextcloud": 1, "collabora": 1}

    @pytest.mark.asyncio
    async def test_disabled_probe_persists_expectation_without_result(self):
        mock_redis, pipeline = _mock_pipeline_redis()
        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_erp_sync", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_erp_absences", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_directum", AsyncMock(return_value=None)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=None)),
        ):
            assert await ih.probe_integrations({"redis": mock_redis}) == {}

        state_call = next(
            call
            for call in pipeline.hset.call_args_list
            if call.args == (ih.INTEGRATION_PROBE_STATE_KEY,)
        )
        state = state_call.kwargs["mapping"]
        assert state["keycloak:expected"] == "0"
        assert "keycloak:result" not in state
        assert "keycloak:result_expires_at" not in state
        pipeline.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_probe_advances_attempt_not_completion(self):
        mock_redis, pipeline = _mock_pipeline_redis()
        with (
            patch.object(
                ih,
                "_probe_keycloak",
                AsyncMock(side_effect=asyncio.CancelledError),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await ih.probe_integrations({"redis": mock_redis})

        mock_redis.hset.assert_awaited_once()
        assert mock_redis.hset.call_args.args[:2] == (
            ih.INTEGRATION_PROBE_STATE_KEY,
            "keycloak:last_attempt",
        )
        pipeline.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_probe_exception_does_not_crash(self):
        """Исключение в probe → интерпретируется как down (0), не падает."""
        mock_redis, _pipeline = _mock_pipeline_redis()
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=True)),
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
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)

        assert len(results) == 5  # вычислены, просто не записаны

    @pytest.mark.asyncio
    async def test_redis_write_error_swallowed(self):
        """Ошибка записи в Redis → не роняет cron."""
        mock_redis, pipeline = _mock_pipeline_redis()
        pipeline.execute = AsyncMock(side_effect=Exception("redis down"))
        ctx = {"redis": mock_redis}

        with (
            patch.object(ih, "_probe_keycloak", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_nextcloud", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_smtp", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_collabora", AsyncMock(return_value=True)),
            patch.object(ih, "_probe_erp_approvals", AsyncMock(return_value=True)),
        ):
            results = await ih.probe_integrations(ctx)  # no exception

        assert len(results) == 5


class TestProbeKeycloak:
    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self):
        fake_kc = MagicMock(keycloak_url="", keycloak_realm="")
        with patch("app.services.keycloak.settings._get_kc_settings", return_value=fake_kc):
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
            patch("app.services.keycloak.settings._get_kc_settings", return_value=fake_kc),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await ih._probe_keycloak()
        assert result is True

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        fake_kc = MagicMock(keycloak_url="http://kc:8080", keycloak_realm="portal")

        class _BoomClient:
            def __await__(self):
                raise TimeoutError()

        with (
            patch("app.services.keycloak.settings._get_kc_settings", return_value=fake_kc),
            patch("httpx.AsyncClient", side_effect=TimeoutError),
        ):
            result = await ih._probe_keycloak()
        assert result is False


class TestProbeSmtp:
    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self):
        fake_cfg = MagicMock()
        fake_cfg.host = ""
        with patch("app.services.email_settings.read_email_settings", return_value=fake_cfg):
            result = await ih._probe_smtp()
        assert result is None

    @pytest.mark.asyncio
    async def test_connection_failed_returns_false(self):
        fake_cfg = MagicMock(host="smtp.example.local", port=25)
        with (
            patch("app.services.email_settings.read_email_settings", return_value=fake_cfg),
            patch("asyncio.open_connection", side_effect=ConnectionRefusedError),
        ):
            result = await ih._probe_smtp()
        assert result is False


class _ProbeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class _ProbeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class TestProbeCollabora:
    @staticmethod
    def _settings(**over):
        values = dict(
            nextcloud_url="https://nc.test",
            nc_service_username="portal-svc",
            nc_service_app_password="app-password",
        )
        values.update(over)
        return SimpleNamespace(**values)

    @staticmethod
    def _ocs_payload(wopi_url="https://office.test"):
        return {
            "ocs": {
                "meta": {"statuscode": 100},
                "data": {"capabilities": {"richdocuments": {"config": {"wopi_url": wopi_url}}}},
            }
        }

    async def _run(self, nc_responses, collabora_responses=(), *, settings=None, enabled=True):
        modules = MagicMock()
        modules.nextcloud.enabled = enabled
        nc_client = _ProbeClient(nc_responses)
        collabora_client = _ProbeClient(collabora_responses)
        clients = [nc_client, collabora_client]
        client_factory = MagicMock(side_effect=clients)
        nc_client.factory = client_factory
        with (
            patch("app.core.modules_config.load_modules", return_value=modules),
            patch(
                "app.core.system_config.load_system_settings",
                return_value=settings or self._settings(),
            ),
            patch("httpx.AsyncClient", client_factory),
        ):
            result = await ih._probe_collabora()
        return result, nc_client, collabora_client

    @pytest.mark.asyncio
    async def test_disabled_returns_none_without_http(self):
        modules = MagicMock()
        modules.nextcloud.enabled = False
        with (
            patch("app.core.modules_config.load_modules", return_value=modules),
            patch("httpx.AsyncClient") as client,
        ):
            assert await ih._probe_collabora() is None
        client.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "field", ["nextcloud_url", "nc_service_username", "nc_service_app_password"]
    )
    async def test_enabled_missing_configuration_is_down(self, field):
        settings = self._settings(**{field: ""})
        result, nc_client, _ = await self._run([], settings=settings)
        assert result is False
        assert nc_client.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [302, 401, 404])
    async def test_nextcloud_redirect_auth_or_missing_app_is_down(self, status):
        result, _nc, collabora = await self._run([_ProbeResponse(status, {})])
        assert result is False
        assert collabora.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            ValueError("html"),
            {},
            {"ocs": {"meta": {"statuscode": 997}, "data": {}}},
            {"ocs": {"meta": {"statuscode": 100}, "data": {"capabilities": {}}}},
        ],
    )
    async def test_invalid_or_missing_richdocuments_capability_is_down(self, payload):
        result, _nc, collabora = await self._run([_ProbeResponse(200, payload)])
        assert result is False
        assert collabora.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wopi_url",
        [
            "",
            "file:///tmp/office",
            "https://user:secret@office.test",
            "https://office.test/path#fragment",
            "https://office.test/proxy.php?unexpected=yes",
        ],
    )
    async def test_unsafe_wopi_url_is_down(self, wopi_url):
        result, _nc, collabora = await self._run([_ProbeResponse(200, self._ocs_payload(wopi_url))])
        assert result is False
        assert collabora.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("wopi_url", "expected_url"),
        [
            ("https://office.test", "https://office.test/hosting/capabilities"),
            (
                "https://nc.test/apps/richdocumentscode/proxy.php?req=",
                "https://nc.test/apps/richdocumentscode/proxy.php?req=/hosting/capabilities",
            ),
        ],
    )
    async def test_valid_external_and_builtin_code_are_up(self, wopi_url, expected_url):
        result, nc_client, collabora = await self._run(
            [_ProbeResponse(200, self._ocs_payload(wopi_url))],
            [_ProbeResponse(200, {"productVersion": "24.04.9.2"})],
        )
        assert result is True
        assert nc_client.calls[0][0].endswith("/ocs/v1.php/cloud/capabilities?format=json")
        assert isinstance(nc_client.calls[0][1]["auth"], ih.httpx.BasicAuth)
        assert nc_client.calls[0][1]["headers"]["OCS-APIRequest"] == "true"
        assert collabora.calls == [(expected_url, {"headers": {"Accept": "application/json"}})]
        assert "auth" not in collabora.calls[0][1]
        assert nc_client.factory.call_count == 2
        for call in nc_client.factory.call_args_list:
            assert call.kwargs == {"timeout": ih._PROBE_TIMEOUT, "follow_redirects": False}

    @pytest.mark.asyncio
    async def test_two_hops_share_one_total_timeout(self):
        real_timeout = asyncio.timeout
        with patch.object(ih.asyncio, "timeout", wraps=real_timeout) as total_timeout:
            result, _nc, _collabora = await self._run(
                [_ProbeResponse(200, self._ocs_payload())],
                [_ProbeResponse(200, {"productVersion": "24.04.9.2"})],
            )
        assert result is True
        total_timeout.assert_called_once_with(ih._PROBE_TIMEOUT)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            _ProbeResponse(302, {}),
            _ProbeResponse(404, {}),
            _ProbeResponse(200, ValueError("not json")),
            _ProbeResponse(200, {}),
            _ProbeResponse(200, {"productVersion": ""}),
        ],
    )
    async def test_collabora_redirect_missing_or_invalid_payload_is_down(self, response):
        result, _nc, _collabora = await self._run(
            [_ProbeResponse(200, self._ocs_payload())], [response]
        )
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failed_hop", ["nextcloud", "collabora"])
    async def test_network_failure_at_each_hop_is_down(self, failed_hop):
        nc_responses = [TimeoutError("timeout")]
        collabora_responses = []
        if failed_hop == "collabora":
            nc_responses = [_ProbeResponse(200, self._ocs_payload())]
            collabora_responses = [TimeoutError("timeout")]
        result, _nc, _collabora = await self._run(nc_responses, collabora_responses)
        assert result is False


class TestProbeErpApprovals:
    """Зонд доступности 1С-согласования: gating модуля/настроек + ping.

    Зонд импортирует зависимости внутри функции (конвенция этого модуля),
    поэтому patch-таргеты — исходные модули, а не ih.*."""

    row_base = "https://erp.test/MageErp/hs/PortalAuth"

    @staticmethod
    def _row(**over) -> SimpleNamespace:
        values = dict(
            base_url="https://erp.test/MageErp/hs/PortalAuth",
            token_base_url=None,
            auth_username="Portal",
            auth_password_enc="enc",
        )
        values.update(over)
        return SimpleNamespace(**values)

    @staticmethod
    def _patches(
        *,
        enabled=True,
        row="default",
        password="pw",
        ping_result=(True, "ok", 10),
        ping_exc=None,
        db_exc=None,
    ) -> list:
        modules = MagicMock()
        modules.approvals.enabled = enabled

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        session_cls = (
            MagicMock(side_effect=db_exc) if db_exc else MagicMock(return_value=_FakeSession())
        )
        row = TestProbeErpApprovals._row() if row == "default" else row
        ping = AsyncMock(side_effect=ping_exc) if ping_exc else AsyncMock(return_value=ping_result)
        return [
            patch("app.core.modules_config.load_modules", return_value=modules),
            patch("app.core.database.AsyncSessionLocal", session_cls),
            patch(
                "app.services.approvals.settings.load_approvals_settings",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.approvals.settings.decrypt_password",
                lambda _row: password,
            ),
            patch("app.services.approvals.client.ping", ping),
        ]

    @staticmethod
    async def _run(patches: list):
        import contextlib

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return await ih._probe_erp_approvals()

    @pytest.mark.asyncio
    async def test_module_disabled_returns_none(self):
        assert await self._run(self._patches(enabled=False)) is None

    @pytest.mark.asyncio
    async def test_load_modules_failure_returns_none(self):
        with patch("app.core.modules_config.load_modules", side_effect=RuntimeError("boom")):
            result = await ih._probe_erp_approvals()
        assert result is None

    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self):
        row = self._row(auth_password_enc=None)
        assert await self._run(self._patches(row=row)) is None

    @pytest.mark.asyncio
    async def test_row_none_returns_none(self):
        assert await self._run(self._patches(row=None)) is None

    @pytest.mark.asyncio
    async def test_db_failure_returns_false(self):
        assert await self._run(self._patches(db_exc=RuntimeError("db down"))) is False

    @pytest.mark.asyncio
    async def test_undecryptable_password_returns_false(self):
        """Настроено, но пароль не расшифровывается (SECRET_KEY сменился) —
        это реальная поломка модуля: False (алерт), а не None (no data)."""
        assert await self._run(self._patches(password=None)) is False

    @pytest.mark.asyncio
    async def test_ping_ok_returns_true(self):
        assert await self._run(self._patches()) is True

    @pytest.mark.asyncio
    async def test_ping_down_returns_false(self):
        result = await self._run(self._patches(ping_result=(False, "ERP недоступна", 0)))
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_exception_returns_false(self):
        assert await self._run(self._patches(ping_exc=RuntimeError("boom"))) is False

    @pytest.mark.asyncio
    async def test_ping_receives_sentinel_login_and_token_base(self):
        """Зонд шлёт заведомо несопоставленный логин (токены не выдаются);
        пустой token_base_url подменяется base_url — как в API."""
        import contextlib

        ping = AsyncMock(return_value=(True, "ok", 1))
        patches = self._patches()
        patches[-1] = patch("app.services.approvals.client.ping", ping)
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await ih._probe_erp_approvals()
        assert ping.await_count == 1
        base_url, token_base_url, auth, login = ping.await_args.args
        assert base_url == self.row_base
        assert token_base_url == self.row_base  # token_base_url пуст → base_url
        assert auth == ("Portal", "pw")
        assert login == ih.ERP_APPROVALS_PROBE_LOGIN
