"""Tests for the meetings feature-flag plumbing in /modules and bootstrap."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


class TestMeetingsModuleIn:
    def test_defaults(self):
        from app.api.modules import MeetingsModuleIn

        m = MeetingsModuleIn()
        assert m.enabled is False
        assert m.calendar_start_hour == 8
        assert m.calendar_end_hour == 19
        assert m.max_recurrence_horizon_days == 31
        assert m.min_search_chars == 3

    def test_bounds(self):
        from pydantic import ValidationError

        from app.api.modules import MeetingsModuleIn

        with pytest.raises(ValidationError):
            MeetingsModuleIn(calendar_start_hour=-1)
        with pytest.raises(ValidationError):
            MeetingsModuleIn(calendar_start_hour=24)
        with pytest.raises(ValidationError):
            MeetingsModuleIn(calendar_end_hour=0)
        with pytest.raises(ValidationError):
            MeetingsModuleIn(calendar_end_hour=25)
        with pytest.raises(ValidationError):
            MeetingsModuleIn(min_search_chars=0)
        with pytest.raises(ValidationError):
            MeetingsModuleIn(min_search_chars=11)


class TestMeetingsModuleOut:
    def test_meetings_field_in_modules_endpoint(self, authed_client_factory):
        async def _run():
            ac, _ = authed_client_factory(role="reader")
            with patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as load:
                from app.api.modules import AllModuleSettings

                load.return_value = AllModuleSettings()
                r = await ac.get("/api/v1/modules")
            assert r.status_code == 200
            body = r.json()
            assert "meetings" in body
            assert "calendar_start_hour" in body["meetings"]
            assert "min_search_chars" in body["meetings"]
            return body

        import asyncio

        body = asyncio.get_event_loop().run_until_complete(_run())
        assert body["meetings"]["enabled"] is False


class TestUpdateMeetingsModuleEndpoint:
    async def test_non_admin_gets_403(self, authed_client_factory):
        ac, _ = authed_client_factory(role="editor")
        r = await ac.put("/api/v1/admin/modules/meetings", json={"enabled": True})
        assert r.status_code == 403

    async def test_admin_updates_meetings(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        with (
            patch("app.api.modules.load_modules_shared", new_callable=AsyncMock) as mock_load,
            patch("app.api.modules._save_modules"),
            patch("app.api.modules.bump_version", new_callable=AsyncMock),
            patch("app.api.modules.push_audit_event", new_callable=AsyncMock),
        ):
            from app.api.modules import AllModuleSettings

            mock_load.return_value = AllModuleSettings()
            r = await ac.put(
                "/api/v1/admin/modules/meetings",
                json={
                    "enabled": True,
                    "calendar_start_hour": 9,
                    "calendar_end_hour": 20,
                    "max_recurrence_horizon_days": 60,
                    "min_search_chars": 2,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["calendar_start_hour"] == 9
        assert body["min_search_chars"] == 2

    async def test_invalid_hour_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="admin")
        r = await ac.put(
            "/api/v1/admin/modules/meetings",
            json={"enabled": True, "calendar_start_hour": 99},
        )
        assert r.status_code == 422


class TestBootstrapMeetingsRegression:
    """Regression: bootstrap MUST include `meetings` in AllModuleSettingsOut.

    Otherwise pydantic raises ValidationError, asyncio.gather swallows it,
    and all modules collapse to disabled defaults — the original bug that
    hid the meetings module from the UI.
    """

    async def test_bootstrap_returns_meetings_field(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")

        from app.core.modules_config import (
            AllModuleSettings,
            MeetingsModuleSettings,
            NextcloudModuleSettings,
            PhotosModuleSettings,
        )

        settings = AllModuleSettings(
            nextcloud=NextcloudModuleSettings(enabled=False),
            photos=PhotosModuleSettings(enabled=True),
            meetings=MeetingsModuleSettings(enabled=True, calendar_start_hour=10),
        )

        with (
            patch(
                "app.api.bootstrap.load_modules_shared",
                new_callable=AsyncMock,
                return_value=settings,
            ),
            patch(
                "app.api.bootstrap.load_system_settings_shared",
                new_callable=AsyncMock,
            ) as mock_sys,
            patch(
                "app.api.bootstrap.get_unread_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            from app.core.system_config import SystemSettings

            mock_sys.return_value = SystemSettings()
            r = await ac.get("/api/v1/bootstrap")

        assert r.status_code == 200
        body = r.json()
        assert "meetings" in body["modules"]
        # The bug was: meetings missing → fallback to defaults (enabled=False).
        # Here the loaded settings have enabled=True; that must propagate.
        assert body["modules"]["meetings"]["enabled"] is True
        assert body["modules"]["meetings"]["calendar_start_hour"] == 10
