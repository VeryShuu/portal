"""Test MeetingsGuard: returns 404 when meetings module disabled."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


class TestMeetingsGuard:
    async def test_disabled_returns_404(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        from app.core.modules_config import (
            AllModuleSettings,
            MeetingsModuleSettings,
        )

        settings = AllModuleSettings(
            meetings=MeetingsModuleSettings(enabled=False)
        )
        with patch(
            "app.api.meetings.load_modules_shared",
            new_callable=AsyncMock,
            return_value=settings,
        ):
            r = await ac.get("/api/v1/meetings/rooms")
        assert r.status_code == 404
        assert "disabled" in r.json().get("detail", "").lower()

    async def test_enabled_allows_through(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        from app.core.modules_config import (
            AllModuleSettings,
            MeetingsModuleSettings,
        )

        settings = AllModuleSettings(
            meetings=MeetingsModuleSettings(enabled=True)
        )
        with patch(
            "app.api.meetings.load_modules_shared",
            new_callable=AsyncMock,
            return_value=settings,
        ):
            r = await ac.get("/api/v1/meetings/rooms")
        # Module enabled → guard passes (200 with empty list from _fake_db).
        assert r.status_code != 404
