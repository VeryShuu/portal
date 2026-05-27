"""TST-04: Unlinking an instance from a series must emit CANCEL(old UID) +
REQUEST(new UID).

When a single occurrence is detached from a recurring series, calendars expect
a CANCEL for the original `series-…@…` UID followed by a REQUEST with the new
per-instance `{id}@…` UID. Otherwise zombie events linger.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_booking():
    room = SimpleNamespace(name="R", email=None, timezone="Europe/Moscow", link=None)
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="x",
        description=None,
        organizer_name="Org",
        start_time=datetime(2030, 6, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2030, 6, 1, 11, 0, tzinfo=UTC),
        series_id=None,
        recurrence_rule=None,
        update_count=1,
        rooms=[SimpleNamespace(room=room)],
        invited_users=[{"user_id": "u1", "full_name": "A", "email": "a@x.com"}],
    )


@pytest.fixture
def patched_env():
    # Eager-import modules that read system settings at import time so our
    # patch below does not interfere with their loading.
    import app.core.database
    import app.services.meetings.notifications  # noqa: F401

    cfg = SimpleNamespace(
        portal_base_url="https://portal.local",
        timezone="Europe/Moscow",
        log_level="INFO",
        log_force_json=False,
    )
    ical_mod = ModuleType("app.services.meetings.ical_builder")

    calls: list[dict] = []

    def fake_build_ical(booking, method, company_domain, from_email, **kwargs):
        uid = kwargs.get("uid_override") or (
            f"series-{booking.series_id}@{company_domain}"
            if booking.series_id is not None
            else f"{booking.id}@{company_domain}"
        )
        calls.append({"method": method, "uid": uid})
        return f"BEGIN:VCALENDAR\nMETHOD:{method}\nUID:{uid}\nEND:VCALENDAR".encode()

    ical_mod.build_ical = fake_build_ical

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.begin = lambda: session  # context manager

    enqueue = AsyncMock()

    outbox_mod = ModuleType("app.services.email_outbox")
    outbox_mod.KIND_MEETING = "meeting"
    outbox_mod.encode_ical_bytes = lambda b: b.decode("utf-8")
    outbox_mod.enqueue_outbox_email = enqueue

    with (
        patch.dict(
            sys.modules,
            {
                "app.services.meetings.ical_builder": ical_mod,
                "app.services.email_outbox": outbox_mod,
            },
        ),
        patch("app.core.system_config.load_system_settings", return_value=cfg),
        patch(
            "app.services.meetings.notifications._get_from_email",
            return_value="portal@x",
        ),
        patch("app.core.database.AsyncSessionLocal", return_value=session),
    ):
        yield {"calls": calls, "enqueue": enqueue}


async def test_unlink_emits_cancel_old_uid_then_request_new_uid(patched_env):
    from app.services.meetings.bookings_service import BookingDiff
    from app.services.meetings.notifications import dispatch_meeting_emails

    booking = _make_booking()
    old_series_id = uuid.uuid4()
    diff = BookingDiff(old_series_uid=f"series-{old_series_id}@portal.local")

    await dispatch_meeting_emails(booking=booking, action="updated", diff=diff)

    calls = patched_env["calls"]
    methods = [c["method"] for c in calls]
    assert "CANCEL" in methods, f"expected CANCEL emission, got {methods}"
    assert "REQUEST" in methods, f"expected REQUEST emission, got {methods}"

    cancel_uids = [c["uid"] for c in calls if c["method"] == "CANCEL"]
    request_uids = [c["uid"] for c in calls if c["method"] == "REQUEST"]
    assert any(
        f"series-{old_series_id}@" in uid for uid in cancel_uids
    ), f"CANCEL must use the OLD series UID, got: {cancel_uids}"
    assert any(
        f"{booking.id}@" in uid for uid in request_uids
    ), f"REQUEST must use the NEW per-instance UID, got: {request_uids}"
