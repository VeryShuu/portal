"""Integration-тесты RSVP-инджеста: apply_reply (матчинг/упsert/дедуп) и
дайджест-логика на реальной БД (savepoint-изоляция tests/db_fixtures.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


def _invited(email: str, full_name: str = "Participant") -> list[dict]:
    return [{"user_id": str(uuid.uuid4()), "full_name": full_name, "email": email}]


def _slot(hours_from_now: float) -> tuple[datetime, datetime]:
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=hours_from_now)
    return start, start + timedelta(hours=1)


async def _make_booking(
    db,
    *,
    creator_id=None,
    invited: list[dict] | None = None,
    series_id: uuid.UUID | None = None,
    start_hours_from_now: float = 2,
    title: str = "RSVP Test",
) -> object:
    from app.models.meetings import MeetingBooking

    start, end = _slot(start_hours_from_now)
    booking = MeetingBooking(
        title=title,
        organizer_name="Org",
        creator_id=creator_id,
        start_time=start,
        end_time=end,
        invited_users=invited or [],
        series_id=series_id,
        update_count=0,
    )
    db.add(booking)
    await db.flush()
    return booking


def _parsed(
    *,
    uid: str,
    attendee: str = "part@x.com",
    status: str = "accepted",
    recurrence_id: datetime | None = None,
    message_id: str | None = None,
):
    from app.services.meetings.rsvp_parser import ParsedReply

    return ParsedReply(
        message_id=message_id or f"<{uuid.uuid4()}@mail>",
        sender_email=attendee,
        attendee_email=attendee,
        status=status,
        uid=uid,
        recurrence_id=recurrence_id,
    )


class TestApplyReply:
    async def test_single_booking_applied_then_duplicate(self, real_db_session, real_user):
        from app.services.meetings.rsvp_ingest import apply_reply, load_rsvp_map

        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("part@x.com", "Part")
        )
        parsed = _parsed(uid=f"{booking.id}@portal.mage.ru")

        outcome = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert outcome.status == "applied"
        assert len(outcome.changes) == 1
        change = outcome.changes[0]
        assert change.booking_id == booking.id
        assert change.creator_id == real_user.id
        assert change.participant_name == "Part"
        assert change.status == "accepted"

        rsvp_map = await load_rsvp_map(real_db_session, [booking.id])
        info = rsvp_map[booking.id]["part@x.com"]
        assert info.status == "accepted"

        # Повтор того же письма — дубликат, ничего не меняется.
        duplicate = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert duplicate.status == "duplicate"
        assert not duplicate.changes

    async def test_not_invited_participant_ignored(self, real_db_session, real_user):
        from app.services.meetings.rsvp_ingest import apply_reply

        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("a@x.com")
        )
        parsed = _parsed(uid=f"{booking.id}@portal.mage.ru", attendee="stranger@x.com")

        outcome = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert outcome.status == "not_invited"

    async def test_unknown_booking_not_found(self, real_db_session):
        from app.services.meetings.rsvp_ingest import apply_reply

        parsed = _parsed(uid=f"{uuid.uuid4()}@portal.mage.ru")
        outcome = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert outcome.status == "not_found"

    async def test_series_reply_without_recurrence_applies_to_future_only(
        self, real_db_session, real_user
    ):
        from sqlalchemy import select

        from app.models.meetings import MeetingRsvp
        from app.services.meetings.rsvp_ingest import apply_reply

        series_id = uuid.uuid4()
        b_past = await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com"),
            series_id=series_id,
            start_hours_from_now=-24,
        )
        b_next1 = await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com"),
            series_id=series_id,
            start_hours_from_now=2,
        )
        b_next2 = await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com"),
            series_id=series_id,
            start_hours_from_now=3,
        )

        parsed = _parsed(uid=f"series-{series_id}@portal.mage.ru")
        outcome = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert outcome.status == "applied"
        assert {c.booking_id for c in outcome.changes} == {b_next1.id, b_next2.id}

        rows = (await real_db_session.execute(select(MeetingRsvp))).scalars().all()
        assert {r.booking_id for r in rows} == {b_next1.id, b_next2.id}
        assert b_past.id not in {r.booking_id for r in rows}

    async def test_series_reply_with_recurrence_matches_single_instance(
        self, real_db_session, real_user
    ):
        from app.services.meetings.rsvp_ingest import apply_reply

        series_id = uuid.uuid4()
        b_first = await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com"),
            series_id=series_id,
            start_hours_from_now=2,
        )
        await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com"),
            series_id=series_id,
            start_hours_from_now=3,
        )

        parsed = _parsed(
            uid=f"series-{series_id}@portal.mage.ru",
            recurrence_id=b_first.start_time,
        )
        outcome = await apply_reply(real_db_session, parsed, parsed.message_id)
        assert outcome.status == "applied"
        assert [c.booking_id for c in outcome.changes] == [b_first.id]

    async def test_participant_changed_mind_updates_status(self, real_db_session, real_user):
        from app.services.meetings.rsvp_ingest import apply_reply, load_rsvp_map

        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("part@x.com")
        )
        first = _parsed(uid=f"{booking.id}@portal.mage.ru", status="accepted")
        await apply_reply(real_db_session, first, first.message_id)

        second = _parsed(uid=f"{booking.id}@portal.mage.ru", status="declined")
        outcome = await apply_reply(real_db_session, second, second.message_id)
        assert outcome.status == "applied"  # изменение статуса — событие

        rsvp_map = await load_rsvp_map(real_db_session, [booking.id])
        assert rsvp_map[booking.id]["part@x.com"].status == "declined"

    async def test_same_status_resend_is_not_a_change(self, real_db_session, real_user):
        from app.services.meetings.rsvp_ingest import apply_reply

        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("part@x.com")
        )
        first = _parsed(uid=f"{booking.id}@portal.mage.ru", status="accepted")
        await apply_reply(real_db_session, first, first.message_id)

        # Другое письмо (новый message_id), тот же статус — не спамим уведомлениями.
        repeat = _parsed(uid=f"{booking.id}@portal.mage.ru", status="accepted")
        outcome = await apply_reply(real_db_session, repeat, repeat.message_id)
        assert outcome.status == "ignored"
        assert not outcome.changes


class TestDigests:
    async def test_final_window_sends_full_list_and_marks(self, real_db_session, real_user):
        from sqlalchemy import select

        from app.models.email_outbox import EmailOutbox
        from app.services.meetings.rsvp_ingest import apply_reply
        from app.worker.tasks.meetings.rsvp_digest import process_final_window

        booking = await _make_booking(
            real_db_session,
            creator_id=real_user.id,
            invited=_invited("part@x.com", "Part") + _invited("silent@x.com", "Silent"),
            # В окно [now+15m, now+16m)
            start_hours_from_now=15.5 / 60,
        )
        accepted = _parsed(uid=f"{booking.id}@portal.mage.ru", status="accepted")
        await apply_reply(real_db_session, accepted, accepted.message_id)

        now = datetime.now(UTC)
        sent = await process_final_window(real_db_session, now=now)
        assert sent == 1
        await real_db_session.flush()

        outbox_rows = (
            (
                await real_db_session.execute(
                    select(EmailOutbox).where(EmailOutbox.related_resource_id == booking.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(outbox_rows) == 1
        body = outbox_rows[0].body_html
        assert "Part" in body and "✅ Принял" in body
        assert "Silent" in body and "⚪ Не ответил" in body

        # Идемпотентность: метка стоит, вторая попытка ничего не шлёт.
        assert booking.rsvp_final_digest_sent_at is not None
        assert await process_final_window(real_db_session, now=now) == 0

    async def test_digest_window_sends_event_email(self, real_db_session, real_user):
        from sqlalchemy import select

        from app.models.email_outbox import EmailOutbox
        from app.services.meetings.rsvp_ingest import apply_reply
        from app.worker.tasks.meetings.rsvp_digest import collect_digest_emails

        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("part@x.com", "Part")
        )
        parsed = _parsed(uid=f"{booking.id}@portal.mage.ru", status="declined")
        await apply_reply(real_db_session, parsed, parsed.message_id)

        now = datetime.now(UTC)
        sent = await collect_digest_emails(
            real_db_session, window_start=now - timedelta(minutes=30), now=now
        )
        assert sent == 1
        await real_db_session.flush()

        row = (
            (
                await real_db_session.execute(
                    select(EmailOutbox).where(EmailOutbox.related_resource_id == booking.id)
                )
            )
            .scalars()
            .one()
        )
        assert real_user.email in row.to_email
        assert "отклонил" in row.body_html

    async def test_digest_skips_creator_with_notify_email_off(self, real_db_session, real_user):
        from app.services.meetings.rsvp_ingest import apply_reply
        from app.worker.tasks.meetings.rsvp_digest import collect_digest_emails

        real_user.notify_email = False
        booking = await _make_booking(
            real_db_session, creator_id=real_user.id, invited=_invited("part@x.com")
        )
        parsed = _parsed(uid=f"{booking.id}@portal.mage.ru")
        await apply_reply(real_db_session, parsed, parsed.message_id)

        now = datetime.now(UTC)
        sent = await collect_digest_emails(
            real_db_session, window_start=now - timedelta(minutes=30), now=now
        )
        assert sent == 0
