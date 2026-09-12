"""Unit-тесты API Directum (``GET/PUT /directum/settings``, ``POST /directum/test``)
и схемных валидаций. Паттерн ``test_matrix_bot_settings_api.py``: прямые вызовы
endpoint-функций с мок-БД (SimpleNamespace-строки), без HTTP-приложения.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.api.directum.runs import get_run, list_runs
from app.api.directum.settings import (
    check_connection,
    get_settings,
    put_settings,
)
from app.schemas.directum import DirectumSettingsIn


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email="admin@mage.ru", role="admin")


def _row(**over) -> SimpleNamespace:
    values = dict(
        enabled=False,
        base_url="https://sed.mage.ru/Integration/odata",
        auth_username=None,
        auth_password_enc=None,
        overdue_run_hours=[],
        expected_interval_days=2,
        notify_emails=None,
        overdue_enabled=False,
        updated_at=datetime.now(UTC),
    )
    values.update(over)
    return SimpleNamespace(**values)


def _configured_row() -> SimpleNamespace:
    return _row(enabled=True, auth_username="PDC1\\svc", auth_password_enc="enc")


def _make_db(row: SimpleNamespace | None) -> tuple[MagicMock, SimpleNamespace | None]:
    db = MagicMock()
    result = MagicMock()
    # sync.load_directum_settings использует scalar_one_or_none(), runs —
    # scalars().one_or_none(); покрываем оба стиля доступа.
    result.scalar_one_or_none.return_value = row
    result.scalars.return_value.one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db, row


class TestGetSettings:
    async def test_defaults_unconfigured(self):
        db, _ = _make_db(_row())
        out = await get_settings(_admin(), db)
        assert out.enabled is False
        assert out.password_set is False
        assert out.configured is False
        assert out.base_url == "https://sed.mage.ru/Integration/odata"

    async def test_configured_flags(self):
        db, _ = _make_db(_configured_row())
        out = await get_settings(_admin(), db)
        assert out.configured is True
        assert out.password_set is True
        assert out.auth_username == "PDC1\\svc"


class TestPutSettings:
    async def test_password_write_only_keeps_previous(self):
        db, row = _make_db(_row(auth_password_enc="prev-enc"))
        with (
            patch("app.api.directum.settings.encrypt_secret") as enc_mock,
            patch("app.api.directum.settings.push_audit_event", new=AsyncMock()) as audit_mock,
        ):
            out = await put_settings(
                DirectumSettingsIn(enabled=True, auth_username="PDC1\\svc"),
                _admin(),
                db,
                MagicMock(),
            )
        enc_mock.assert_not_called()
        assert row.auth_password_enc == "prev-enc"
        assert out.configured is True
        audit_mock.assert_awaited_once()

    async def test_new_password_encrypts(self):
        db, row = _make_db(_row())
        with (
            patch("app.api.directum.settings.encrypt_secret", return_value="new-enc") as enc_mock,
            patch("app.api.directum.settings.push_audit_event", new=AsyncMock()),
        ):
            await put_settings(
                DirectumSettingsIn(enabled=True, auth_username="PDC1\\svc", auth_password="secret"),
                _admin(),
                db,
                MagicMock(),
            )
        enc_mock.assert_called_once_with("secret")
        assert row.auth_password_enc == "new-enc"

    async def test_enabled_without_credentials_400(self):
        db, _ = _make_db(_row())
        with (
            patch("app.api.directum.settings.push_audit_event", new=AsyncMock()),
            pytest.raises(Exception) as ei,
        ):
            await put_settings(DirectumSettingsIn(enabled=True), _admin(), db, MagicMock())
        assert getattr(ei.value, "status_code", None) == 400
        detail = str(ei.value.detail)
        for field in ("auth_username", "auth_password"):
            assert field in detail

    async def test_disabled_without_credentials_ok(self):
        """Выключенный модуль можно сохранять с пустыми кредами (черновик)."""
        db, _ = _make_db(_row())
        with patch("app.api.directum.settings.push_audit_event", new=AsyncMock()):
            out = await put_settings(DirectumSettingsIn(enabled=False), _admin(), db, MagicMock())
        assert out.enabled is False


class TestConnectionEndpoint:
    async def test_not_configured_generic_error(self):
        db, _ = _make_db(_row())
        result = await check_connection(_admin(), db)
        assert result.ok is False
        assert "not configured" in (result.error or "").lower()

    async def test_auth_failure_hint(self):
        from app.services.directum.odata import DirectumApiError

        db, _ = _make_db(_configured_row())
        with (
            patch("app.api.directum.settings.decrypt_secret", return_value="pw"),
            patch(
                "app.api.directum.settings.ping",
                AsyncMock(side_effect=DirectumApiError("401", status_code=401)),
            ) as ping_mock,
        ):
            result = await check_connection(_admin(), db)
        ping_mock.assert_awaited_once()
        assert result.ok is False
        assert "service account" in (result.error or "").lower()

    async def test_unreachable_hint(self):
        from app.services.directum.odata import DirectumTransportError

        db, _ = _make_db(_configured_row())
        with (
            patch("app.api.directum.settings.decrypt_secret", return_value="pw"),
            patch(
                "app.api.directum.settings.ping",
                AsyncMock(side_effect=DirectumTransportError("boom")),
            ),
        ):
            result = await check_connection(_admin(), db)
        assert result.ok is False
        assert "unreachable" in (result.error or "").lower()

    async def test_success_detail(self):
        db, row = _make_db(_configured_row())
        with (
            patch("app.api.directum.settings.decrypt_secret", return_value="pw"),
            patch("app.api.directum.settings.ping", AsyncMock(return_value=1)),
        ):
            result = await check_connection(_admin(), db)
        assert result.ok is True
        assert row.base_url in (result.detail or "")


class TestRunsEndpoints:
    async def test_list_runs(self):
        run_obj = SimpleNamespace(
            id=1,
            triggered_by="cron",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            status="success",
            tasks_total=5,
            performers_total=2,
            users_notified=1,
            users_skipped_opt_in=1,
            users_unmatched=0,
            users_ambiguous=0,
            errors=0,
            report={"notified": []},
        )
        db = MagicMock()
        count_res = MagicMock()
        count_res.scalar_one.return_value = 1
        rows_res = MagicMock()
        rows_res.scalars.return_value.all.return_value = [run_obj]
        db.execute = AsyncMock(side_effect=[count_res, rows_res])
        out = await list_runs(_admin(), db, limit=20, offset=0)
        assert out.total == 1
        assert out.items[0].id == 1
        assert out.items[0].report == {"notified": []}

    async def test_get_run_not_found_404(self):
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        with pytest.raises(Exception) as ei:
            await get_run(999, _admin(), db)
        assert getattr(ei.value, "status_code", None) == 404


class TestSettingsInValidation:
    def test_base_url_requires_scheme(self):
        with pytest.raises(ValidationError):
            DirectumSettingsIn(base_url="sed.mage.ru/Integration/odata")

    def test_base_url_trailing_slash_stripped(self):
        dto = DirectumSettingsIn(base_url="https://sed.mage.ru/odata/")
        assert dto.base_url == "https://sed.mage.ru/odata"

    def test_username_stripped(self):
        dto = DirectumSettingsIn(auth_username="  PDC1\\svc\n")
        assert dto.auth_username == "PDC1\\svc"

    def test_username_whitespace_only_becomes_none(self):
        dto = DirectumSettingsIn(auth_username="   ")
        assert dto.auth_username is None

    def test_password_stripped(self):
        dto = DirectumSettingsIn(auth_password=" secret \n")
        assert dto.auth_password == "secret"

    def test_password_whitespace_only_becomes_none(self):
        dto = DirectumSettingsIn(auth_password="   ")
        assert dto.auth_password is None

    def test_notify_emails_cleaned(self):
        dto = DirectumSettingsIn(notify_emails=[" a@mage.ru ", "", "  ", "b@mage.ru"])
        assert dto.notify_emails == ["a@mage.ru", "b@mage.ru"]

    def test_notify_emails_empty_list_becomes_none(self):
        dto = DirectumSettingsIn(notify_emails=["  ", ""])
        assert dto.notify_emails is None

    def test_run_hours_range_validated(self):
        with pytest.raises(ValidationError):
            DirectumSettingsIn(overdue_run_hours=[24])
        with pytest.raises(ValidationError):
            DirectumSettingsIn(overdue_run_hours=[-1])

    def test_run_hours_dedup_sorted(self):
        dto = DirectumSettingsIn(overdue_run_hours=[14, 10, 14, 12])
        assert dto.overdue_run_hours == [10, 12, 14]


class TestModuleToggle:
    async def test_update_directum_module_saves_and_audits(self):
        from app.api.modules import DirectumModuleIn, update_directum_module

        saved: list = []
        with (
            patch(
                "app.api.modules.load_modules_shared",
                AsyncMock(return_value=SimpleNamespace(directum=None)),
            ),
            patch("app.api.modules._save_modules", side_effect=lambda m: saved.append(m)),
            patch("app.api.modules.bump_version", AsyncMock()) as bump_mock,
            patch("app.api.modules._emit_audit", AsyncMock()) as audit_mock,
        ):
            out = await update_directum_module(
                DirectumModuleIn(enabled=True), _admin(), MagicMock()
            )

        assert out.enabled is True
        assert saved[0].directum.enabled is True
        bump_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()


class TestRunNowEndpoint:
    def _make_request(self, pool) -> SimpleNamespace:
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))

    async def test_not_configured_400(self):
        from app.api.directum.run import run_now

        db, _ = _make_db(_row())
        with pytest.raises(Exception) as ei:
            await run_now(_admin(), db, self._make_request(None))
        assert getattr(ei.value, "status_code", None) == 400

    async def test_module_disabled_400(self):
        """Кнопка при выключенном «Модуль включён» даёт мгновенную 400, а не
        молчаливый скип в воркере (инцидент «крутится и ничего»)."""
        from app.api.directum.run import run_now

        db, _ = _make_db(_row(auth_username="u", auth_password_enc="enc"))
        with pytest.raises(Exception) as ei:
            await run_now(_admin(), db, self._make_request(None))
        assert getattr(ei.value, "status_code", None) == 400
        assert "off" in str(ei.value.detail)

    async def test_no_pool_503(self):
        from app.api.directum.run import run_now

        db, _ = _make_db(_configured_row())
        with pytest.raises(Exception) as ei:
            await run_now(_admin(), db, self._make_request(None))
        assert getattr(ei.value, "status_code", None) == 503

    async def test_queued_with_unique_job_id(self):
        """job-id уникален на каждое нажатие (uuid-суффикс) — ARQ-дедуп по
        фиксированному id больше не глотает повторы в течение часа."""
        from app.api.directum.run import run_now

        db, _ = _make_db(_configured_row())
        pool = MagicMock()
        job = SimpleNamespace(job_id="directum:run:42:abc123def456")
        pool.enqueue_job = AsyncMock(return_value=job)
        out = await run_now(_admin(), db, self._make_request(pool))
        assert out.status == "queued"
        assert out.job_id == "directum:run:42:abc123def456"
        # В _job_id передан уникальный суффикс.
        passed_id = pool.enqueue_job.call_args.kwargs["_job_id"]
        assert passed_id.startswith("directum:run:")
        assert passed_id.count(":") == 3

    async def test_none_job_returns_queued_without_id(self):
        from app.api.directum.run import run_now

        db, _ = _make_db(_configured_row())
        pool = MagicMock()
        pool.enqueue_job = AsyncMock(return_value=None)  # коллизия id (почти невозможна)
        out = await run_now(_admin(), db, self._make_request(pool))
        assert out.status == "queued"
        assert out.job_id is None


class TestSingletonDefensiveCreate:
    async def test_get_settings_creates_row_when_missing(self):
        db, _ = _make_db(None)
        created: list = []
        db.add = created.append

        async def _flush() -> None:
            # Симулируем БД-дефолты после flush (server_default/python default).
            for obj in created:
                obj.enabled = False
                obj.base_url = "https://sed.mage.ru/Integration/odata"
                obj.auth_username = None
                obj.auth_password_enc = None
                obj.overdue_run_hours = []
                obj.expected_interval_days = 2
                obj.notify_emails = None
                obj.overdue_enabled = False
                obj.updated_at = datetime.now(UTC)

        db.flush = _flush
        out = await get_settings(_admin(), db)
        assert out.enabled is False
        assert len(created) == 1


class TestOdataClientLifecycle:
    async def test_init_close_roundtrip(self):
        from app.services.directum import odata

        await odata.init_directum_http_client()
        client = odata._get_client()
        assert client is not None and not client.is_closed
        # Повторный init не пересоздает живой клиент.
        await odata.init_directum_http_client()
        assert odata._get_client() is client
        await odata.close_directum_http_client()
        assert odata._DIRECTUM_HTTP_CLIENT is None


class TestScheduleValidation:
    async def test_overdue_enabled_without_hours_400(self):
        """UX-урок «молчаливое ничегонеделанье»: включённая задача без часов
        расписания никогда бы не запускалась — PUT отклоняет сразу."""
        db, _ = _make_db(_row())
        with (
            patch("app.api.directum.settings.push_audit_event", new=AsyncMock()),
            pytest.raises(Exception) as ei,
        ):
            await put_settings(
                DirectumSettingsIn(
                    enabled=True,
                    auth_username="PDC1\\svc",
                    auth_password="pw",
                    overdue_enabled=True,
                    overdue_run_hours=[],
                ),
                _admin(),
                db,
                MagicMock(),
            )
        assert getattr(ei.value, "status_code", None) == 400
        assert "run hour" in str(ei.value.detail)

    async def test_overdue_enabled_with_hours_ok(self):
        db, _ = _make_db(_row())
        with patch("app.api.directum.settings.push_audit_event", new=AsyncMock()):
            out = await put_settings(
                DirectumSettingsIn(
                    enabled=True,
                    auth_username="PDC1\\svc",
                    auth_password="pw",
                    overdue_enabled=True,
                    overdue_run_hours=[11, 13],
                ),
                _admin(),
                db,
                MagicMock(),
            )
        assert out.overdue_run_hours == [11, 13]
