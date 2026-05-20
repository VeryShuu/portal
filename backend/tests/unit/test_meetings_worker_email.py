"""TST-02: send_meeting_email worker task must complete without TypeError (BLK-02).

`push_meetings_audit` is keyword-only and opens its own session; calling it
with a positional `db` argument was the original bug. This test ensures the
worker task runs end-to-end with mocked SMTP + audit and writes an EMAIL_SENT
audit entry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_send_meeting_email_writes_audit_without_typeerror() -> None:
    from app.worker.tasks.meetings.email import send_meeting_email

    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    fake_modules = type("M", (), {"meetings": type("Mt", (), {"enabled": True})()})()

    with (
        patch(
            "app.worker.tasks.meetings.email.load_smtp_config",
            return_value={
                "from_address": "noreply@portal.local",
                "host": "smtp",
                "port": 25,
                "username": "",
                "password": "",
                "use_tls": False,
                "use_starttls": False,
            },
        ),
        patch(
            "app.worker.tasks.meetings.email.smtp_send",
            new=AsyncMock(return_value=None),
        ),
        patch("app.core.modules_config.load_modules", return_value=fake_modules),
        patch("app.services.meetings.audit.push_meetings_audit", new=fake_audit),
    ):
        await send_meeting_email(
            {"job_try": 1},
            to_email="alice@example.com",
            subject="Hello",
            html_body="<p>Hi</p>",
            ical_bytes=b"BEGIN:VCALENDAR\nEND:VCALENDAR",
            method="REQUEST",
        )

    assert audit_calls, "expected EMAIL_SENT audit entry"
    entry = audit_calls[-1]
    # All callers must use keyword-only signature: no positional db arg.
    assert "db" not in entry
    assert entry.get("action") is not None
    details = entry.get("details") or {}
    assert details.get("to") == "alice@example.com"
    assert details.get("method") == "REQUEST"
