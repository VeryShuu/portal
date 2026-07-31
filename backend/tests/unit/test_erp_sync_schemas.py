"""Unit-тесты для ERP-sync module: схемы + module-gate (docs/wip/erp-sync.md).

Покрытие:
- ErpSyncSettingsIn / ErpSyncSettingsOut: defaults, write-only password
- ErpSyncRunOut: валидация triggered_by/status
- ErpSyncRunNowResponse / ErpSyncTestResult
- AllModuleSettings: erp_sync.enabled default False (module-gate wiring)
- ErpSyncModuleSettings / ErpSyncModuleIn/Out (api/modules.py)
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


# ── Module-gate (modules_config + api/modules) ──────────────────────────────


class TestErpSyncModuleGate:
    def test_module_settings_default_disabled(self):
        from app.core.modules_config import ErpSyncModuleSettings

        m = ErpSyncModuleSettings()
        assert m.enabled is False

    def test_all_module_settings_includes_erp_sync(self):
        from app.core.modules_config import AllModuleSettings

        m = AllModuleSettings()
        assert hasattr(m, "erp_sync")
        assert m.erp_sync.enabled is False

    def test_all_module_settings_parse_erp_sync_from_json(self):
        from app.core.modules_config import AllModuleSettings

        m = AllModuleSettings.model_validate({"erp_sync": {"enabled": True}})
        assert m.erp_sync.enabled is True

    def test_all_module_settings_drops_unknown_keys_silently(self):
        """erp_sync отсутствует в JSON → default (False)."""
        from app.core.modules_config import AllModuleSettings

        m = AllModuleSettings.model_validate({})
        assert m.erp_sync.enabled is False

    def test_erp_sync_module_in_out_models(self):
        from app.api.modules import ErpSyncModuleIn, ErpSyncModuleOut

        out = ErpSyncModuleOut(enabled=True)
        assert out.enabled is True
        assert ErpSyncModuleIn(enabled=False).enabled is False


# ── Settings schemas ─────────────────────────────────────────────────────────


class TestErpSyncSettingsSchemas:
    def test_settings_in_defaults(self):
        from app.schemas.erp_sync import ErpSyncSettingsIn

        s = ErpSyncSettingsIn()
        assert s.enabled is False
        assert s.poll_interval_seconds == 900
        assert s.expected_interval_days == 4
        assert s.notify_emails is None
        assert s.poll_enabled is False
        # IMAP вынесен в общие настройки (ADR-048) — per-module остались фильтры.
        assert s.mail_subject_filter is None
        assert s.mail_sender_filter is None
        assert s.mail_attachment_filter is None

    def test_settings_in_poll_interval_bounds(self):
        from pydantic import ValidationError

        from app.schemas.erp_sync import ErpSyncSettingsIn

        with pytest.raises(ValidationError):
            ErpSyncSettingsIn(poll_interval_seconds=30)  # ниже 60
        with pytest.raises(ValidationError):
            ErpSyncSettingsIn(poll_interval_seconds=4000)  # выше 3600
        # Границы включены
        assert ErpSyncSettingsIn(poll_interval_seconds=60).poll_interval_seconds == 60
        assert ErpSyncSettingsIn(poll_interval_seconds=3600).poll_interval_seconds == 3600

    def test_settings_out_defaults(self):
        from app.schemas.erp_sync import ErpSyncSettingsOut

        s = ErpSyncSettingsOut()
        assert s.enabled is False
        assert s.poll_interval_seconds == 900
        # IMAP-полей в Out больше нет (переехали во вкладку Email).
        assert not hasattr(s, "imap_host")
        assert not hasattr(s, "imap_password_set")

    def test_settings_out_no_imap_fields(self):
        """ADR-048: IMAP вынесен в общие настройки — в ErpSyncSettingsOut
        нет ни imap-полей, ни plaintext-пароля."""
        from app.schemas.erp_sync import ErpSyncSettingsOut

        fields = set(ErpSyncSettingsOut.model_fields.keys())
        for imap_field in (
            "imap_host",
            "imap_port",
            "imap_username",
            "imap_password",
            "imap_password_enc",
            "imap_password_set",
            "imap_folder",
            "imap_use_ssl",
        ):
            assert imap_field not in fields


# ── Run schemas ──────────────────────────────────────────────────────────────


class TestErpSyncRunSchemas:
    def test_run_out_validates_triggered_by(self):
        from pydantic import ValidationError

        from app.schemas.erp_sync import ErpSyncRunOut

        base = {
            "id": 1,
            "triggered_by": "cron",
            "started_at": "2026-07-31T10:00:00+00:00",
            "status": "success",
        }
        # Валидные значения
        assert ErpSyncRunOut.model_validate(base).triggered_by == "cron"
        base["triggered_by"] = "manual"
        assert ErpSyncRunOut.model_validate(base).triggered_by == "manual"
        # Недопустимое
        base["triggered_by"] = "scheduler"
        with pytest.raises(ValidationError):
            ErpSyncRunOut.model_validate(base)

    def test_run_out_validates_status(self):
        from pydantic import ValidationError

        from app.schemas.erp_sync import ErpSyncRunOut

        base = {
            "id": 1,
            "triggered_by": "cron",
            "started_at": "2026-07-31T10:00:00+00:00",
            "status": "partial",
        }
        for ok in ("success", "partial", "failed", "skipped"):
            base["status"] = ok
            assert ErpSyncRunOut.model_validate(base).status == ok
        base["status"] = "running"
        with pytest.raises(ValidationError):
            ErpSyncRunOut.model_validate(base)

    def test_run_out_report_defaults_empty(self):
        from app.schemas.erp_sync import ErpSyncRunOut

        run = ErpSyncRunOut.model_validate(
            {
                "id": 1,
                "triggered_by": "manual",
                "started_at": "2026-07-31T10:00:00+00:00",
                "status": "success",
            }
        )
        assert run.report == {}

    def test_run_list_shape(self):
        from app.schemas.erp_sync import ErpSyncRunList

        lst = ErpSyncRunList(items=[], total=0)
        assert lst.items == []
        assert lst.total == 0


# ── Misc response schemas ────────────────────────────────────────────────────


class TestErpSyncMiscSchemas:
    def test_run_now_response(self):
        from app.schemas.erp_sync import ErpSyncRunNowResponse

        r = ErpSyncRunNowResponse(status="queued", job_id="abc")
        assert r.status == "queued"
        assert r.job_id == "abc"
        assert r.run_id is None
