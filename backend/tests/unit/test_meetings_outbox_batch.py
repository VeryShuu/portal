"""Tests for the batch outbox INSERT (audit M3).

Главный DoD M3: создание встречи с N участниками → ровно 1 batch-INSERT в
outbox (вместо N round-trip). Проверяется через вызов ``enqueue_outbox_email_batch``
с ``items`` списком, длина которого = число уникальных invited emails.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _ical_builder_mock() -> ModuleType:
    mod = ModuleType("app.services.meetings.ical_builder")
    mod.build_ical = MagicMock(return_value=b"VCAL")  # type: ignore[attr-defined]
    return mod


def _make_session_cm():
    """Полноценная mock-сессия с __aenter__/__aexit__ + begin() (mirror extra-файла).

    dispatch_meeting_emails делает ``async with AsyncSessionLocal() as session,
    session.begin():`` — нужен и контекст-менеджер, и NestedTransaction-like begin.
    """
    db_mock = AsyncMock()
    db_mock.__aenter__ = AsyncMock(return_value=db_mock)
    db_mock.__aexit__ = AsyncMock(return_value=None)
    db_mock.get = AsyncMock(return_value=None)

    begin_mock = AsyncMock()
    begin_mock.__aenter__ = AsyncMock()
    begin_mock.__aexit__ = AsyncMock()
    db_mock.begin = MagicMock(return_value=begin_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm, db_mock


def _make_booking(invited_emails: list[str], room_email: str | None = None):
    room = SimpleNamespace(name="Room A", email=room_email, timezone="Europe/Moscow", link=None)
    br = SimpleNamespace(room=room) if room_email else None
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Test Meeting",
        description=None,
        organizer_name="Organiser",
        start_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        series_id=None,
        recurrence_rule=None,
        update_count=0,
        rooms=[br] if br else [],
        invited_users=[
            {"user_id": str(uuid.uuid4()), "full_name": f"U{i}", "email": addr}
            for i, addr in enumerate(invited_emails)
        ],
    )


class TestBatchInsertOnCreated:
    """Created-branch: все invited уходят одним batch-вызовом."""

    @pytest.fixture(autouse=True)
    def _patch_env(self):
        cfg = SimpleNamespace(
            portal_base_url="https://portal.local", timezone="Europe/Moscow", log_level="INFO"
        )
        mock_mod = _ical_builder_mock()
        with (
            patch.dict(sys.modules, {"app.services.meetings.ical_builder": mock_mod}),
            patch("app.core.system_config.load_system_settings", return_value=cfg),
            patch(
                "app.services.meetings.notifications._get_from_email",
                return_value="portal@c.local",
            ),
            patch(
                "app.services.meetings.notifications._load_organizer",
                AsyncMock(return_value=None),
            ),
        ):
            yield

    async def test_50_recipients_single_batch_insert(self):
        """DoD M3: 50 участников → ровно 1 batch-вызов с 50 OutboxItem.

        Раньше было 50 отдельных ``enqueue_outbox_email`` (50 round-trip к БД);
        теперь — один multi-row INSERT через ``enqueue_outbox_email_batch``.
        """
        from app.services.meetings.notifications import dispatch_meeting_emails

        emails = [f"user{i}@test.com" for i in range(50)]
        booking = _make_booking(emails)

        single_mock = AsyncMock()
        batch_mock = AsyncMock(return_value=[])
        session_cm, _db_mock = _make_session_cm()

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", single_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
        ):
            await dispatch_meeting_emails(booking=booking, action="created")

        # Главный assertion M3: ровно ОДИН batch-вызов (один round-trip).
        assert batch_mock.call_count == 1
        # items — позиционный args[1], содержит ровно 50 строк (без rooms/organizer).
        batch_items = batch_mock.call_args.args[1]
        assert len(batch_items) == 50
        batch_emails = {item.to_email for item in batch_items}
        assert batch_emails == set(emails)
        # Все items одного kind (meeting) и один method (REQUEST для created).
        assert {item.kind for item in batch_items} == {"meeting"}
        assert {item.payload["method"] for item in batch_items} == {"REQUEST"}
        # Single-enqueue не должен вызываться для invited (только organizer/rooms).
        assert single_mock.call_count == 0

    async def test_zero_recipients_no_batch_call(self):
        """Пустой список invited → batch не вызывается (no-op)."""
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking([])
        single_mock = AsyncMock()
        batch_mock = AsyncMock(return_value=[])
        session_cm, _db_mock = _make_session_cm()

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", single_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
        ):
            await dispatch_meeting_emails(booking=booking, action="created")

        assert batch_mock.call_count == 0

    async def test_duplicate_emails_deduplicated_in_batch(self):
        """Дубли emails дедуплицируются до batch-вызова (прежняя семантика)."""
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(["dup@test.com", "dup@test.com", "uniq@test.com"])

        single_mock = AsyncMock()
        batch_mock = AsyncMock(return_value=[])
        session_cm, _db_mock = _make_session_cm()

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", single_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
        ):
            await dispatch_meeting_emails(booking=booking, action="created")

        batch_items = batch_mock.call_args.args[1]
        batch_emails = [item.to_email for item in batch_items]
        assert sorted(batch_emails) == ["dup@test.com", "uniq@test.com"]

    async def test_cancelled_uses_cancel_method_in_batch(self):
        """Cancelled-branch: batch-items получают method=CANCEL."""
        from app.services.meetings.notifications import dispatch_meeting_emails

        booking = _make_booking(["a@test.com", "b@test.com"])

        single_mock = AsyncMock()
        batch_mock = AsyncMock(return_value=[])
        session_cm, _db_mock = _make_session_cm()

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", single_mock),
            patch("app.services.email_outbox.enqueue_outbox_email_batch", batch_mock),
        ):
            await dispatch_meeting_emails(booking=booking, action="cancelled")

        batch_items = batch_mock.call_args.args[1]
        assert len(batch_items) == 2
        assert {item.payload["method"] for item in batch_items} == {"CANCEL"}


async def test_enqueue_outbox_email_batch_empty_list_is_noop():
    """enqueue_outbox_email_batch([]) → no DB call, returns []."""
    from app.services.email_outbox import enqueue_outbox_email_batch

    session = AsyncMock()
    result = await enqueue_outbox_email_batch(session, [])
    assert result == []
    session.execute.assert_not_called()


async def test_enqueue_outbox_email_batch_returns_uuids_from_returning():
    """Batch-INSERT с RETURNING id возвращает список UUID (по одному на строку)."""
    from app.services.email_outbox import OutboxItem, enqueue_outbox_email_batch

    session = AsyncMock()
    returned_ids = [uuid.uuid4(), uuid.uuid4()]
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=returned_ids)
    rows_mock = MagicMock()
    rows_mock.scalars = MagicMock(return_value=scalars_mock)
    session.execute = AsyncMock(return_value=rows_mock)

    items = [
        OutboxItem(kind="meeting", to_email="a@test.com", subject="S", body_html="H"),
        OutboxItem(kind="meeting", to_email="b@test.com", subject="S", body_html="H"),
    ]
    result = await enqueue_outbox_email_batch(session, items)

    assert result == returned_ids
    assert session.execute.call_count == 1
