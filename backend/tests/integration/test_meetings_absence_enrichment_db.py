"""Integration-тесты absence-enrichment для приглашённых на встречу.

Покрытие:
- :func:`enrich_absences_for_invited` находит отсутствие, действующее на дату
  встречи, и возвращает :class:`AbsenceInfo` с приоритетной категорией.
- приоритет sick > vacation > business_trip при пересечении отсутствий.
- внешние участники (``source == 'external'``) пропускаются.
- :func:`current_status_snapshot` читает ``users.current_status`` для live-поиска.
- :func:`booking_to_out` обогащает ``InvitedUser.absence`` на дату встречи.

Требует INTEGRATION_DB=true (testcontainers / реальная БД с erp_absences).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from app.api.meetings._mappers import booking_to_out
from app.models.erp_sync import ErpAbsence
from app.models.user import User
from app.schemas.meetings import BookingCreate, InvitedUser, RoomCreate
from app.services.meetings.absence_enrichment import (
    current_status_snapshot,
    enrich_absences_for_invited,
)
from app.services.meetings.bookings_service import create_booking
from app.services.meetings.rooms_service import create_room

pytestmark = pytest.mark.asyncio


async def _create_user(session, **overrides) -> User:
    defaults = dict(
        email=f"abs-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test User",
        role="reader",
        auth_source="local",
        current_status="working",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    return user


async def _create_absence(
    session,
    *,
    user_id,
    kind: str = "vacation_main",
    start: date,
    end: date,
) -> ErpAbsence:
    absence = ErpAbsence(
        user_id=user_id,
        kind=kind,
        position="Инженер",
        department="Отдел",
        start_date=start,
        end_date=end,
        source="erp_sync",
    )
    session.add(absence)
    await session.flush()
    return absence


async def _invited(email: str, full_name: str = "User", source: str = "keycloak") -> InvitedUser:
    return InvitedUser(
        user_id=str(uuid.uuid4()),
        full_name=full_name,
        email=email,
        source=source,  # type: ignore[arg-type]
    )


class TestEnrichAbsencesForInvited:
    async def test_finds_absence_active_on_meeting_date(self, real_db_session):
        """Возвращает отсутствие, действующее на дату встречи."""
        user = await _create_user(real_db_session, email="meet1@example.com")
        meeting_date = date.today() + timedelta(days=5)
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind="vacation_main",
            start=meeting_date - timedelta(days=1),
            end=meeting_date + timedelta(days=3),
        )

        invited = [await _invited("meet1@example.com")]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)

        assert "meet1@example.com" in result
        info = result["meet1@example.com"]
        assert info.category == "vacation"
        assert info.end_date == meeting_date + timedelta(days=3)

    async def test_absence_not_active_on_meeting_date_excluded(self, real_db_session):
        """Отсутствие, не пересекающееся с датой встречи, не возвращается."""
        user = await _create_user(real_db_session, email="meet2@example.com")
        meeting_date = date.today() + timedelta(days=30)
        # Отсутствие давно закончилось.
        await _create_absence(
            real_db_session,
            user_id=user.id,
            start=meeting_date - timedelta(days=20),
            end=meeting_date - timedelta(days=10),
        )

        invited = [await _invited("meet2@example.com")]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)
        assert result == {}

    async def test_external_participants_skipped(self, real_db_session):
        """Внешние участники (source=external) не обогащаются."""
        meeting_date = date.today()
        invited = [
            await _invited("guest@external.com", source="external"),
            await _invited("nobody@example.com"),  # нет в БД — не найдется
        ]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)
        assert result == {}

    async def test_priority_sick_beats_vacation(self, real_db_session):
        """Больной в отпуске → категория sick (приоритет выше)."""
        user = await _create_user(real_db_session, email="meet3@example.com")
        meeting_date = date.today() + timedelta(days=5)
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind="vacation_main",
            start=meeting_date - timedelta(days=2),
            end=meeting_date + timedelta(days=10),
        )
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind="sick",
            start=meeting_date - timedelta(days=1),
            end=meeting_date + timedelta(days=2),
        )

        invited = [await _invited("meet3@example.com")]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)
        assert result["meet3@example.com"].category == "sick"

    async def test_priority_vacation_beats_business_trip(self, real_db_session):
        """В отпуске и в командировке → категория vacation."""
        user = await _create_user(real_db_session, email="meet4@example.com")
        meeting_date = date.today() + timedelta(days=5)
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind="business_trip",
            start=meeting_date - timedelta(days=1),
            end=meeting_date + timedelta(days=3),
        )
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind="day_off_paid",
            start=meeting_date - timedelta(days=1),
            end=meeting_date + timedelta(days=3),
        )

        invited = [await _invited("meet4@example.com")]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)
        assert result["meet4@example.com"].category == "vacation"

    async def test_empty_invited_returns_empty(self, real_db_session):
        result = await enrich_absences_for_invited(real_db_session, [], on_date=date.today())
        assert result == {}

    async def test_multiple_users_one_query(self, real_db_session):
        """Bulk: все отсутствующие сотрудники в одном запросе."""
        u1 = await _create_user(real_db_session, email="bulk1@example.com")
        u2 = await _create_user(real_db_session, email="bulk2@example.com")
        await _create_user(real_db_session, email="bulk3@example.com")  # без отсутствия
        meeting_date = date.today() + timedelta(days=5)
        await _create_absence(
            real_db_session,
            user_id=u1.id,
            kind="sick",
            start=meeting_date,
            end=meeting_date + timedelta(days=2),
        )
        await _create_absence(
            real_db_session,
            user_id=u2.id,
            kind="business_trip",
            start=meeting_date,
            end=meeting_date + timedelta(days=2),
        )

        invited = [
            await _invited("bulk1@example.com"),
            await _invited("bulk2@example.com"),
            await _invited("bulk3@example.com"),
        ]
        result = await enrich_absences_for_invited(real_db_session, invited, on_date=meeting_date)
        assert set(result.keys()) == {"bulk1@example.com", "bulk2@example.com"}
        assert result["bulk1@example.com"].category == "sick"
        assert result["bulk2@example.com"].category == "business_trip"


class TestCurrentStatusSnapshot:
    async def test_reads_users_current_status(self, real_db_session):
        """current_status_snapshot берёт users.current_status (как справочник)."""
        await _create_user(
            real_db_session,
            email="snap1@example.com",
            current_status="vacation",
            current_status_until=date.today() + timedelta(days=5),
        )
        await _create_user(real_db_session, email="snap2@example.com", current_status="working")

        result = await current_status_snapshot(
            real_db_session, ["snap1@example.com", "snap2@example.com"]
        )
        assert "snap1@example.com" in result
        assert result["snap1@example.com"].category == "vacation"
        # working не попадает в результат.
        assert "snap2@example.com" not in result

    async def test_empty_emails_returns_empty(self, real_db_session):
        assert await current_status_snapshot(real_db_session, []) == {}


@pytest_asyncio.fixture
async def room(real_db_session):
    return await create_room(real_db_session, RoomCreate(name=f"R-{uuid.uuid4().hex[:6]}"))


class TestBookingToOutEnrichment:
    """Сквозная проверка: booking_to_out обогащает InvitedUser.absence на дату встречи."""

    async def test_absence_filled_on_meeting_date(self, real_db_session, real_user, room):
        """Участник с отсутствием на дату встречи → absence заполнен в BookingOut."""
        meeting_date = date.today() + timedelta(days=5)
        start = datetime.combine(meeting_date, datetime.min.time()).replace(hour=10, tzinfo=UTC)
        absent_user = await _create_user(real_db_session, email="bout1@example.com")
        await _create_absence(
            real_db_session,
            user_id=absent_user.id,
            kind="vacation_main",
            start=meeting_date,
            end=meeting_date + timedelta(days=3),
        )

        booking = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="T",
                start_time=start,
                end_time=start + timedelta(hours=1),
                room_ids=[room.id],
                invited_users=[
                    InvitedUser(
                        user_id=str(absent_user.id),
                        full_name="Absent User",
                        email="bout1@example.com",
                    )
                ],
            ),
            user=real_user,
        )

        out = await booking_to_out(real_db_session, booking)
        assert len(out.invited_users) == 1
        assert out.invited_users[0].absence is not None
        assert out.invited_users[0].absence.category == "vacation"

    async def test_no_absence_when_working(self, real_db_session, real_user, room):
        """Сотрудник без отсутствия на дату встречи → absence=None."""
        meeting_date = date.today() + timedelta(days=5)
        start = datetime.combine(meeting_date, datetime.min.time()).replace(hour=11, tzinfo=UTC)
        working_user = await _create_user(real_db_session, email="bout2@example.com")

        booking = await create_booking(
            real_db_session,
            payload=BookingCreate(
                title="T",
                start_time=start,
                end_time=start + timedelta(hours=1),
                room_ids=[room.id],
                invited_users=[
                    InvitedUser(
                        user_id=str(working_user.id),
                        full_name="Working User",
                        email="bout2@example.com",
                    )
                ],
            ),
            user=real_user,
        )

        out = await booking_to_out(real_db_session, booking)
        assert out.invited_users[0].absence is None
