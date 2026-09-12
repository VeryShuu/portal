"""Unit-тесты ARQ-задач Directum (:mod:`app.worker.tasks.directum_sync`).

Проверяются гейты (module.json / settings.enabled / overdue_enabled /
interval-guard / lock), happy-path (вызов сервисного прогона + LAST_SUCCESS),
watchdog и probe. Сессия БД и Redis — моки; сеть не нужна.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import directum_sync as ds


def _settings_row(**over) -> SimpleNamespace:
    values = dict(
        id=1,
        enabled=True,
        base_url="https://sed.test/odata",
        auth_username="PDC1\\svc",
        auth_password_enc="enc",
        overdue_run_hours=[10, 12, 14],
        expected_interval_days=2,
        notify_emails=None,
        overdue_enabled=True,
    )
    values.update(over)
    return SimpleNamespace(**values)


def _make_db(row: SimpleNamespace | None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


class _FakeSessionCtx:
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def _make_redis(*, last_run_hour: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=last_run_hour.encode() if last_run_hour else None)
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock(return_value=1)
    return redis


def _patch_session(row: SimpleNamespace | None):
    return patch.object(ds, "AsyncSessionLocal", lambda: _FakeSessionCtx(_make_db(row)))


def _patch_modules(enabled: bool):
    async def _fake_load(redis):
        return SimpleNamespace(directum=SimpleNamespace(enabled=enabled))

    return patch(
        "app.core.modules_config.load_modules_shared",
        new=_fake_load,
    )


def _run_mock(status: str = "success") -> SimpleNamespace:
    return SimpleNamespace(id=9, status=status, tasks_total=3, users_notified=1)


class TestRunDirectumSyncWorker:
    async def test_module_disabled_skips(self):
        redis = _make_redis()
        with _patch_modules(False):
            assert await ds.run_directum_sync({"redis": redis}) == {"skipped": "module_disabled"}

    async def test_no_settings_skips(self):
        with _patch_modules(True), _patch_session(None):
            assert await ds.run_directum_sync({"redis": _make_redis()}) == {
                "skipped": "not_configured"
            }

    async def test_settings_enabled_false_skips(self):
        with _patch_modules(True), _patch_session(_settings_row(enabled=False)):
            assert await ds.run_directum_sync({"redis": _make_redis()}) == {"skipped": "disabled"}

    async def test_missing_credentials_skip(self):
        with _patch_modules(True), _patch_session(_settings_row(auth_password_enc=None)):
            assert await ds.run_directum_sync({"redis": _make_redis()}) == {
                "skipped": "not_configured"
            }

    async def test_cron_overdue_disabled_skips(self):
        with _patch_modules(True), _patch_session(_settings_row(overdue_enabled=False)):
            assert await ds.run_directum_sync({"redis": _make_redis()}) == {
                "skipped": "overdue_disabled"
            }

    async def test_cron_not_scheduled_hour_skips(self):
        with (
            _patch_modules(True),
            _patch_session(_settings_row()),
            patch.object(ds, "_schedule_now", return_value=(15, "2026-08-17 15")),
            patch("app.services.directum.sync.directum_configured", return_value=True),
        ):
            assert await ds.run_directum_sync({"redis": _make_redis()}) == {
                "skipped": "not_scheduled_hour"
            }

    async def test_cron_already_ran_this_hour_skips(self):
        redis = _make_redis(last_run_hour="2026-08-17 10")
        with (
            _patch_modules(True),
            _patch_session(_settings_row()),
            patch.object(ds, "_schedule_now", return_value=(10, "2026-08-17 10")),
            patch("app.services.directum.sync.directum_configured", return_value=True),
        ):
            assert await ds.run_directum_sync({"redis": redis}) == {
                "skipped": "already_ran_this_hour"
            }

    async def test_lock_held_skips(self):
        redis = _make_redis()
        redis.set = AsyncMock(side_effect=lambda *a, **kw: None)  # NX не сработал
        with (
            _patch_modules(True),
            _patch_session(_settings_row()),
            patch("app.services.directum.sync.directum_configured", return_value=True),
        ):
            assert await ds.run_directum_sync({"redis": redis}, triggered_by="manual") == {
                "skipped": "lock_held"
            }

    async def test_manual_happy_path_calls_service(self):
        redis = _make_redis()
        service = AsyncMock(return_value=_run_mock())
        with (
            _patch_modules(True),
            _patch_session(_settings_row()),
            patch("app.services.directum.sync.directum_configured", return_value=True),
            patch.object(ds, "run_directum_sync_service", service),
        ):
            summary = await ds.run_directum_sync({"redis": redis}, triggered_by="manual")

        service.assert_awaited_once()
        assert summary["run_id"] == 9
        assert summary["status"] == "success"
        # LAST_SUCCESS зафиксирован; lock освобождён (Lua compare-and-delete).
        assert redis.set.call_count >= 2
        redis.eval.assert_awaited_once()

    async def test_cron_scheduled_hour_runs(self):
        redis = _make_redis()
        with (
            _patch_modules(True),
            _patch_session(_settings_row()),
            patch("app.services.directum.sync.directum_configured", return_value=True),
            patch.object(ds, "_schedule_now", return_value=(12, "2026-08-17 12")),
            patch.object(ds, "run_directum_sync_service", AsyncMock(return_value=_run_mock())),
        ):
            summary = await ds.run_directum_sync({"redis": redis})
        assert summary["status"] == "success"
        # Ключ дедупа часа записан с TTL.
        redis.set.assert_any_call(
            "directum:last_run_hour", "2026-08-17 12", ex=ds.LAST_RUN_HOUR_TTL
        )


class TestWatchdog:
    async def test_module_disabled_skips(self):
        with _patch_modules(False):
            assert await ds.directum_watchdog({"redis": _make_redis()}) == {
                "skipped": "module_disabled"
            }

    async def test_overdue_disabled_skips(self):
        with _patch_modules(True), _patch_session(_settings_row(overdue_enabled=False)):
            assert await ds.directum_watchdog({"redis": _make_redis()}) == {"skipped": "disabled"}

    @staticmethod
    def _wd_db(run_row: SimpleNamespace | None) -> MagicMock:
        """db.execute: 1-й вызов — settings, 2-й — последний успешный прогон."""
        db = MagicMock()
        settings_res = MagicMock()
        settings_res.scalar_one_or_none.return_value = _settings_row()
        run_res = MagicMock()
        run_res.scalar_one_or_none.return_value = run_row
        db.execute = AsyncMock(side_effect=[settings_res, run_res])
        return db

    async def test_fresh_success_ok(self):
        finished = datetime.now(UTC) - timedelta(hours=1)
        with (
            _patch_modules(True),
            patch.object(
                ds,
                "AsyncSessionLocal",
                lambda: _FakeSessionCtx(self._wd_db(SimpleNamespace(finished_at=finished))),
            ),
        ):
            out = await ds.directum_watchdog({"redis": _make_redis()})
        assert out == {"ok": "recent_success"}

    async def test_stale_alerts(self):
        finished = datetime.now(UTC) - timedelta(days=10)
        alert = AsyncMock()
        with (
            _patch_modules(True),
            patch.object(
                ds,
                "AsyncSessionLocal",
                lambda: _FakeSessionCtx(self._wd_db(SimpleNamespace(finished_at=finished))),
            ),
            patch.object(ds, "_send_watchdog_alert", alert),
        ):
            out = await ds.directum_watchdog({"redis": _make_redis()})
        alert.assert_awaited_once()
        assert out["alerted"] is True

    async def test_no_runs_alerts_never(self):
        alert = AsyncMock()
        with (
            _patch_modules(True),
            patch.object(ds, "AsyncSessionLocal", lambda: _FakeSessionCtx(self._wd_db(None))),
            patch.object(ds, "_send_watchdog_alert", alert),
        ):
            out = await ds.directum_watchdog({"redis": _make_redis()})
        assert out["stale_since"] is None


class TestProbe:
    async def test_module_off_returns_none(self):
        with patch(
            "app.core.modules_config.load_modules",
            return_value=SimpleNamespace(directum=SimpleNamespace(enabled=False)),
        ):
            assert await ds.probe_directum() is None

    @staticmethod
    def _probe_db(run_row: SimpleNamespace | None) -> MagicMock:
        """db.execute: 1-й вызов — settings, 2-й — последний прогон."""
        db = MagicMock()
        settings_res = MagicMock()
        settings_res.scalar_one_or_none.return_value = _settings_row()
        run_res = MagicMock()
        run_res.scalar_one_or_none.return_value = run_row
        db.execute = AsyncMock(side_effect=[settings_res, run_res])
        return db

    async def test_enabled_no_runs_returns_false(self):
        with (
            patch(
                "app.core.modules_config.load_modules",
                return_value=SimpleNamespace(directum=SimpleNamespace(enabled=True)),
            ),
            patch.object(ds, "AsyncSessionLocal", lambda: _FakeSessionCtx(self._probe_db(None))),
        ):
            assert await ds.probe_directum() is False

    async def test_fresh_run_returns_true(self):
        finished = datetime.now(UTC) - timedelta(hours=2)
        run_row = SimpleNamespace(finished_at=finished)
        with (
            patch(
                "app.core.modules_config.load_modules",
                return_value=SimpleNamespace(directum=SimpleNamespace(enabled=True)),
            ),
            patch.object(ds, "AsyncSessionLocal", lambda: _FakeSessionCtx(self._probe_db(run_row))),
        ):
            assert await ds.probe_directum() is True


class TestRequireDirectumModule:
    async def test_disabled_raises_404(self):
        from fastapi import HTTPException

        from app.api.deps import require_directum_module

        with _patch_modules(False), pytest.raises(HTTPException) as ei:
            await require_directum_module(MagicMock())
        assert ei.value.status_code == 404

    async def test_enabled_passes(self):
        from app.api.deps import require_directum_module

        with _patch_modules(True):
            assert await require_directum_module(MagicMock()) is None
