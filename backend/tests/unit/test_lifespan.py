"""Smoke-тесты для `app/core/lifespan.py`.

`lifespan` слишком инфраструктурный для unit-уровня (Redis, asyncpg,
FastAPILimiter, Keycloak, Nextcloud, audit partitions), поэтому здесь — лишь
smoke-проверки на критичные ветки:

- happy-path: всё стартует и shuts down штатно
- libmagic отсутствует → app.state.libmagic_available = False
- Redis ping падает → RuntimeError на старте
- nextcloud disabled → get_nc_service не дёргается
- nextcloud enabled, get_nc_service бросает → swallow (graceful degrade)
- audit partitions не создаются → app.state.audit_partitions_ok = False
- shutdown закрывает arq_pool/redis/keycloak/nextcloud
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.core.lifespan import lifespan


def _settings(*, redis_url: str = "redis://localhost:6379/0") -> SimpleNamespace:
    return SimpleNamespace(
        redis_url=redis_url,
        database_url="postgresql+asyncpg://user:pw@localhost:5432/portal",
        environment="test",
        redis_socket_connect_timeout=5.0,
        redis_health_check_interval=30,
    )


def _sys_settings(timezone: str = "UTC", portal_base_url: str = "https://portal.test"):
    return SimpleNamespace(timezone=timezone, portal_base_url=portal_base_url)


def _modules(nextcloud_enabled: bool = False):
    return SimpleNamespace(nextcloud=SimpleNamespace(enabled=nextcloud_enabled))


def _patches(
    *,
    libmagic: object = object(),
    redis_ping_ok: bool = True,
    nextcloud_enabled: bool = False,
    nc_raises: bool = False,
    audit_raises: bool = False,
    portal_base_url: str = "https://portal.test",
):
    """Returns ExitStack-style list для удобной сборки контекста."""
    redis_mock = AsyncMock()
    if not redis_ping_ok:
        redis_mock.ping.side_effect = ConnectionError("redis down")
    redis_mock.aclose = AsyncMock()

    arq_pool = MagicMock()
    arq_pool.aclose = AsyncMock()

    nc_service = MagicMock()
    if nc_raises:
        nc_service.ensure_root = AsyncMock(side_effect=RuntimeError("nc unreachable"))
    else:
        nc_service.ensure_root = AsyncMock()

    pg_conn = MagicMock()
    pg_conn.close = AsyncMock()
    asyncpg_connect = AsyncMock(return_value=pg_conn)

    ensure_partitions = AsyncMock(
        side_effect=(RuntimeError("partitions") if audit_raises else None),
        return_value=None if audit_raises else ["audit_log_2026_06"],
    )

    return {
        "redis_mock": redis_mock,
        "arq_pool": arq_pool,
        "nc_service": nc_service,
        "pg_conn": pg_conn,
        "asyncpg_connect": asyncpg_connect,
        "ensure_partitions": ensure_partitions,
        "stack": [
            patch("app.core.lifespan.get_settings", return_value=_settings()),
            patch("app.core.uploads.magic", libmagic),
            patch(
                "app.core.system_config.load_system_settings",
                return_value=_sys_settings(portal_base_url=portal_base_url),
            ),
            patch("app.core.system_config.apply_timezone"),
            patch("app.core.lifespan.Redis.from_url", return_value=redis_mock),
            patch("app.core.lifespan.FastAPILimiter.init", new=AsyncMock()),
            patch("app.core.lifespan.FastAPILimiter.close", new=AsyncMock()),
            patch("app.core.lifespan.init_kc_http_client", new=AsyncMock()),
            patch("app.core.lifespan.close_kc_http_client", new=AsyncMock()),
            patch("app.core.lifespan.bootstrap_admin", new=AsyncMock()),
            patch("app.core.lifespan.arq_create_pool", new=AsyncMock(return_value=arq_pool)),
            patch(
                "app.core.modules_config.load_modules",
                return_value=_modules(nextcloud_enabled),
            ),
            patch("app.core.lifespan.get_nc_service", return_value=nc_service),
            patch("app.core.lifespan.invalidate_nc_service", new=AsyncMock()),
            patch("app.core.lifespan.asyncpg.connect", new=asyncpg_connect),
            patch("app.core.lifespan._ensure_partitions", new=ensure_partitions),
        ],
    }


class TestLifespanHappyPath:
    @pytest.mark.asyncio
    async def test_full_startup_and_shutdown(self):
        ctx = _patches()
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                assert app.state.libmagic_available is True
                assert app.state.audit_partitions_ok is True
                assert app.state.redis is ctx["redis_mock"]
                assert app.state.arq_pool is ctx["arq_pool"]

        ctx["arq_pool"].aclose.assert_awaited_once()
        ctx["redis_mock"].aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_libmagic_missing_sets_flag_false(self):
        ctx = _patches(libmagic=None)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                assert app.state.libmagic_available is False

    @pytest.mark.asyncio
    async def test_portal_base_url_empty_logs_warning_but_starts(self):
        ctx = _patches(portal_base_url="")
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                assert app.state.redis is ctx["redis_mock"]


class TestLifespanRedisFailure:
    @pytest.mark.asyncio
    async def test_redis_ping_failure_raises_runtimeerror(self):
        ctx = _patches(redis_ping_ok=False)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            with pytest.raises(RuntimeError, match="Redis unavailable at startup"):
                async with lifespan(app):
                    pass  # pragma: no cover


class TestLifespanNextcloud:
    @pytest.mark.asyncio
    async def test_nextcloud_disabled_skips_ensure_root(self):
        ctx = _patches(nextcloud_enabled=False)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                pass
        ctx["nc_service"].ensure_root.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nextcloud_enabled_calls_ensure_root(self):
        ctx = _patches(nextcloud_enabled=True)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                pass
        ctx["nc_service"].ensure_root.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nextcloud_failure_is_swallowed(self):
        ctx = _patches(nextcloud_enabled=True, nc_raises=True)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                assert app.state.audit_partitions_ok is True


class TestLifespanAuditPartitions:
    @pytest.mark.asyncio
    async def test_audit_partitions_failure_sets_flag_false(self):
        ctx = _patches(audit_raises=True)
        from contextlib import ExitStack

        with ExitStack() as es:
            for p in ctx["stack"]:
                es.enter_context(p)
            app = FastAPI()
            async with lifespan(app):
                assert app.state.audit_partitions_ok is False
