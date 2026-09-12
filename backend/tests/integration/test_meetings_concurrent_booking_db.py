"""Integration: конкурентное бронирование переговорных на реальной PostgreSQL.

Аудит тестирования 2026-08-21 (docs/wip/test-audit-remediation.md, фаза
«модули по прод-риску», meetings). Существующие integration-тесты bookings
проверяют конфликты ПОСЛЕДОВАТЕЛЬНО (создал → создал снова → 409). Реальная
защита — EXCLUDE GIST-констрейнт ``booking_rooms_no_overlap`` + SAVEPOINT в
``_flush_or_conflict`` — срабатывает только когда две транзакции одновременно
прошли pre-check (оба SELECT'а не видели незакоммиченных конкурентов).
Здесь проверяется именно гонка: несколько одновременных бронирований одного
слота через отдельные соединения.

Запуск: ./scripts/test-integration.sh tests/integration/test_meetings_concurrent_booking_db.py
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def _slot(offset_hours: int = 24) -> tuple[datetime, datetime]:
    base = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=offset_hours)
    return base, base + timedelta(hours=1)


async def _create_room_committed(engine: AsyncEngine) -> uuid.UUID:
    from app.schemas.meetings import RoomCreate
    from app.services.meetings.rooms_service import create_room

    async with AsyncSession(engine, expire_on_commit=False) as s:
        room = await create_room(s, RoomCreate(name=f"Race-{uuid.uuid4().hex[:8]}"))
        await s.commit()
        return room.id


async def _create_user_committed(engine: AsyncEngine, email: str) -> uuid.UUID:
    from app.models.user import User

    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = User(
            email=email,
            full_name=f"Race User {email[:6]}",
            role="reader",
            auth_source="local",
            current_status="working",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences={},
            updated_at=datetime.now(UTC),
        )
        s.add(user)
        await s.commit()
        return user.id


@pytest_asyncio.fixture
async def race_cleanup(real_db_engine: AsyncEngine) -> AsyncGenerator[dict, None]:
    """Реестр созданного для коммиченных сущностей; teardown с учётом FK.

    Порядок: bookings (CASCADE убирает meeting_booking_rooms) → rooms → users.
    """
    state: dict = {"bookings": [], "rooms": [], "users": []}
    yield state
    from app.models.meetings import MeetingBooking, MeetingRoom
    from app.models.user import User

    async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
        if state["bookings"]:
            await s.execute(delete(MeetingBooking).where(MeetingBooking.id.in_(state["bookings"])))
        if state["rooms"]:
            await s.execute(delete(MeetingRoom).where(MeetingRoom.id.in_(state["rooms"])))
        if state["users"]:
            await s.execute(delete(User).where(User.id.in_(state["users"])))
        await s.commit()


async def _book_in_own_tx(
    engine: AsyncEngine,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    start: datetime,
    end: datetime,
) -> uuid.UUID:
    """Бронирование в собственной транзакции/соединении (модель воркера-конкурента)."""
    from app.models.user import User
    from app.schemas.meetings import BookingCreate
    from app.services.meetings.bookings_service import create_booking

    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = await s.get(User, user_id)
        assert user is not None
        booking = await create_booking(
            s,
            payload=BookingCreate(title=title, start_time=start, end_time=end, room_ids=[room_id]),
            user=user,
        )
        await s.commit()
        return booking.id


async def _book_rooms_in_own_tx(
    engine: AsyncEngine,
    *,
    room_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    title: str,
    start: datetime,
    end: datetime,
) -> uuid.UUID:
    """Multi-room бронирование в собственной транзакции (порядок комнат значим)."""
    from app.models.user import User
    from app.schemas.meetings import BookingCreate
    from app.services.meetings.bookings_service import create_booking

    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = await s.get(User, user_id)
        assert user is not None
        booking = await create_booking(
            s,
            payload=BookingCreate(
                title=title, start_time=start, end_time=end, room_ids=list(room_ids)
            ),
            user=user,
        )
        await s.commit()
        return booking.id


async def _move_booking_in_own_tx(
    engine: AsyncEngine,
    *,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> None:
    from app.models.user import User
    from app.schemas.meetings import BookingUpdate
    from app.services.meetings.bookings_service import update_booking

    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = await s.get(User, user_id)
        assert user is not None
        await update_booking(
            s,
            booking_id=booking_id,
            payload=BookingUpdate(start_time=start, end_time=end),
            user=user,
        )
        await s.commit()


async def _count_bookings_in_slot(
    engine: AsyncEngine, room_id: uuid.UUID, start: datetime, end: datetime
) -> int:
    """Сколько бронирований занимает слот в комнате (свежий committed-read)."""
    from app.models.meetings import MeetingBookingRoom

    async with AsyncSession(engine, expire_on_commit=False) as s:
        n = (
            await s.execute(
                select(func.count())
                .select_from(MeetingBookingRoom)
                .where(
                    MeetingBookingRoom.room_id == room_id,
                    MeetingBookingRoom.start_time == start,
                    MeetingBookingRoom.end_time == end,
                )
            )
        ).scalar_one()
        return int(n)


async def _wait_for_lock_waiter(
    engine: AsyncEngine,
    waiter_pid: int,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.05,
) -> None:
    """Дождаться, что КОНКРЕТНАЯ сессия (waiter_pid) реально ждёт heavyweight-лок.

    Детерминированный барьер для deadlock-теста (аудит 2026-08-23, P2;
    review-2 P2 — фильтр по PID, а не «любой waiter по таблице»: чужая
    параллельная активность больше не даёт ложного прохода). Факт «A
    заблокировалась на вставке r2@T» подтверждается из pg_stat_activity
    (wait_event_type = 'Lock'), а не слепым sleep'ом. Fail-closed: не
    дождались за timeout — предпосылка клинча не построена.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine, expire_on_commit=False) as poll:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while asyncio.get_running_loop().time() < deadline:
            waiting = (
                await poll.execute(
                    text(
                        """
                        SELECT wait_event_type
                        FROM pg_stat_activity
                        WHERE pid = :pid AND state = 'active'
                        """
                    ),
                    {"pid": waiter_pid},
                )
            ).scalar_one_or_none()
            await poll.rollback()  # не держим idle-in-transaction между опросами
            if waiting == "Lock":
                return
            await asyncio.sleep(poll_interval_s)
    pytest.fail(
        f"за {timeout_s}s сессия {waiter_pid} не встала в ожидание Lock — "
        "предпосылка дедлока не построена"
    )


class TestConcurrentBookingRace:
    async def test_same_slot_same_room_exactly_one_winner(self, real_db_engine, race_cleanup):
        """Гонка 5 бронирований на один слот: ровно один победитель.

        Каждый участник в собственном соединении/транзакции; все pre-check'и
        стартуют до первого commit'а. Гарантию даёт EXCLUDE GIST
        booking_rooms_no_overlap: вставка второго диапазона ждёт коммита
        первого и падает IntegrityError → BookingConflict.
        """
        from app.services.meetings.bookings_service import BookingConflict

        room_id = await _create_room_committed(real_db_engine)
        race_cleanup["rooms"].append(room_id)
        user_ids = []
        for i in range(5):
            uid = await _create_user_committed(
                real_db_engine, f"race-{uuid.uuid4().hex[:8]}-{i}@x.test"
            )
            race_cleanup["users"].append(uid)
            user_ids.append(uid)

        start, end = _slot(offset_hours=48)

        async def _attempt(i: int):
            try:
                booking_id = await _book_in_own_tx(
                    real_db_engine,
                    room_id=room_id,
                    user_id=user_ids[i],
                    title=f"Race {i}",
                    start=start,
                    end=end,
                )
                race_cleanup["bookings"].append(booking_id)
                return booking_id
            except BookingConflict:
                return None

        results = await asyncio.gather(*(_attempt(i) for i in range(5)))

        winners = [r for r in results if r is not None]
        assert len(winners) == 1, (
            f"ровно одно бронирование должно победить, победили: {len(winners)}"
        )
        # и в БД слот занят ровно один раз (никаких двойных бронирований)
        assert await _count_bookings_in_slot(real_db_engine, room_id, start, end) == 1

    async def test_same_slot_different_rooms_both_succeed(self, real_db_engine, race_cleanup):
        """Один слот в разных комнатах — конфликта нет, обе брони проходят."""
        room_a = await _create_room_committed(real_db_engine)
        room_b = await _create_room_committed(real_db_engine)
        race_cleanup["rooms"].extend([room_a, room_b])
        user_id = await _create_user_committed(
            real_db_engine, f"race2-{uuid.uuid4().hex[:8]}@x.test"
        )
        race_cleanup["users"].append(user_id)

        start, end = _slot(offset_hours=49)

        async def _attempt(room_id: uuid.UUID):
            booking_id = await _book_in_own_tx(
                real_db_engine,
                room_id=room_id,
                user_id=user_id,
                title="Parallel rooms",
                start=start,
                end=end,
            )
            race_cleanup["bookings"].append(booking_id)
            return booking_id

        a, b = await asyncio.gather(_attempt(room_a), _attempt(room_b))

        assert a and b and a != b
        assert await _count_bookings_in_slot(real_db_engine, room_a, start, end) == 1
        assert await _count_bookings_in_slot(real_db_engine, room_b, start, end) == 1

    async def test_concurrent_create_vs_move_existing(self, real_db_engine, race_cleanup):
        """Гонка «создание слота» против «перенос существующей брони на тот же слот».

        Оба проходят pre-check одновременно → GIST решает: ровно одна операция
        занимает слот, вторая получает BookingConflict.
        """
        from app.services.meetings.bookings_service import BookingConflict

        room_id = await _create_room_committed(real_db_engine)
        race_cleanup["rooms"].append(room_id)
        owner_id = await _create_user_committed(
            real_db_engine, f"race3-owner-{uuid.uuid4().hex[:8]}@x.test"
        )
        rival_id = await _create_user_committed(
            real_db_engine, f"race3-rival-{uuid.uuid4().hex[:8]}@x.test"
        )
        race_cleanup["users"].extend([owner_id, rival_id])

        parked_start, parked_end = _slot(offset_hours=50)  # где лежит существующая бронь
        race_slot_start, race_slot_end = _slot(offset_hours=51)  # спорный слот

        parked_id = await _book_in_own_tx(
            real_db_engine,
            room_id=room_id,
            user_id=owner_id,
            title="Parked",
            start=parked_start,
            end=parked_end,
        )
        race_cleanup["bookings"].append(parked_id)

        async def _move():
            try:
                await _move_booking_in_own_tx(
                    real_db_engine,
                    booking_id=parked_id,
                    user_id=owner_id,
                    start=race_slot_start,
                    end=race_slot_end,
                )
                return "moved"
            except BookingConflict:
                return None

        async def _create():
            try:
                new_id = await _book_in_own_tx(
                    real_db_engine,
                    room_id=room_id,
                    user_id=rival_id,
                    title="Rival",
                    start=race_slot_start,
                    end=race_slot_end,
                )
                race_cleanup["bookings"].append(new_id)
                return "created"
            except BookingConflict:
                return None

        move_result, create_result = await asyncio.gather(_move(), _create())

        winners = [r for r in (move_result, create_result) if r is not None]
        assert len(winners) == 1, f"спорный слот должен занять ровно один, заняли: {winners}"
        assert (
            await _count_bookings_in_slot(real_db_engine, room_id, race_slot_start, race_slot_end)
            == 1
        )


class TestDeadlockNormalization:
    """Deadlock между конкурентными брони → предсказуемый BookingConflict (409).

    audit-review 2026-08-22 (P1): до фикса серверная терминция транзакции
    (sqlstate 40P01) вылетала из create_booking как DBAPIError → 500.
    Здесь дедлок строится детерминированно: конкурентная транзакция X держит
    GIST-диапазон r2@T, сервисная A заблокировала r1@T и ждёт r2@T, после
    чего X просит r1@T — взаимное ожидание, PG убивает A (эмпирически жертвой
    стабильно становится сторона, присоединившаяся к ожиданию последней).
    """

    async def test_deadlock_in_service_flush_normalized_to_conflict(
        self, real_db_engine, race_cleanup
    ):
        from app.schemas.meetings import BookingCreate
        from app.services.meetings.bookings_service import BookingConflict, create_booking

        user_id = await _create_user_committed(real_db_engine, f"dlk-{uuid.uuid4().hex[:8]}@x.test")
        race_cleanup["users"].append(user_id)
        r1 = await _create_room_committed(real_db_engine)
        r2 = await _create_room_committed(real_db_engine)
        race_cleanup["rooms"].extend([r1, r2])
        start, end = _slot(offset_hours=73)

        # X: незакоммиченная бронь держит диапазон r2@T
        session_x = AsyncSession(real_db_engine, expire_on_commit=False)
        try:
            xb = await session_x.execute(
                text(
                    """
                    INSERT INTO meeting_bookings (
                        title, organizer_name, creator_id, start_time, end_time,
                        invited_users, update_count, created_at, updated_at
                    ) VALUES ('X', 'X', :uid, :s, :e, CAST('[]' AS JSONB), 0, NOW(), NOW())
                    RETURNING id
                    """
                ),
                {"uid": str(user_id), "s": start, "e": end},
            )
            x_booking = xb.scalar_one()
            await session_x.execute(
                text(
                    """
                    INSERT INTO meeting_booking_rooms (booking_id, room_id, start_time, end_time)
                    VALUES (:b, :r, :s, :e)
                    """
                ),
                {"b": str(x_booking), "r": str(r2), "s": start, "e": end},
            )

            from app.models.user import User

            session_a = AsyncSession(real_db_engine, expire_on_commit=False)
            try:
                user_a = await session_a.get(User, user_id)
                # PID сессии A — для точного barrier-фильтра (review-2, P2)
                pid_a = (await session_a.execute(text("SELECT pg_backend_pid()"))).scalar_one()

                async def _service_call():
                    return await create_booking(
                        session_a,
                        payload=BookingCreate(
                            title="A", start_time=start, end_time=end, room_ids=[r1, r2]
                        ),
                        user=user_a,
                    )

                task_a = asyncio.create_task(_service_call())
                # Детерминированный барьер (аудит 2026-08-23, P2): прежде чем
                # строить клинч, ждём подтверждения из pg_stat_activity, что A
                # реально заблокирована на GIST-локе r2@T. Прежний sleep(0.4)
                # был гонкой с планировщиком: на медленной машине X мог
                # коммититься до того, как A успела взять r1 — тест флакал.
                await _wait_for_lock_waiter(real_db_engine, pid_a)

                # X просит r1@T → блокируется на A → дедлок → PG терминирует A
                await session_x.execute(
                    text(
                        """
                        INSERT INTO meeting_booking_rooms (booking_id, room_id, start_time, end_time)
                        VALUES (:b, :r, :s, :e)
                        """
                    ),
                    {"b": str(x_booking), "r": str(r1), "s": start, "e": end},
                )

                with pytest.raises(BookingConflict):
                    await asyncio.wait_for(task_a, timeout=10)
            finally:
                # как get_db: rollback по клинченной (deadlock) сессии прощаем —
                # иначе IllegalStateChangeError замаскирует BookingConflict
                with contextlib.suppress(Exception):
                    await session_a.rollback()
                with contextlib.suppress(Exception):
                    await session_a.close()
        finally:
            await session_x.rollback()
            await session_x.close()

    async def test_reversed_room_order_race_loop_never_500s(self, real_db_engine, race_cleanup):
        """Нагрузочная проверка: реверс-порядок комнат, 15 гонок подряд.

        Каждая итерация обязана закончиться ровно одним победителем, проигравший
        получает BookingConflict — никаких DBAPIError/deadlock наружу.
        """
        from app.services.meetings.bookings_service import BookingConflict

        r1 = await _create_room_committed(real_db_engine)
        r2 = await _create_room_committed(real_db_engine)
        race_cleanup["rooms"].extend([r1, r2])
        user_a = await _create_user_committed(real_db_engine, f"rvsa-{uuid.uuid4().hex[:8]}@x.test")
        user_b = await _create_user_committed(real_db_engine, f"rvsb-{uuid.uuid4().hex[:8]}@x.test")
        race_cleanup["users"].extend([user_a, user_b])

        for i in range(15):
            start, end = _slot(offset_hours=100 + i)

            async def _attempt(
                uid: uuid.UUID,
                rooms: list[uuid.UUID],
                *,
                title: str,
                slot_start: datetime,
                slot_end: datetime,
            ):
                try:
                    booking_id = await _book_rooms_in_own_tx(
                        real_db_engine,
                        room_ids=rooms,
                        user_id=uid,
                        title=title,
                        start=slot_start,
                        end=slot_end,
                    )
                    race_cleanup["bookings"].append(booking_id)
                    return True
                except BookingConflict:
                    return False

            # A брониает [r1, r2], B одновременно [r2, r1] — встречные
            # последовательности GIST-замков (рецепт дедлока)
            ok_a, ok_b = await asyncio.gather(
                _attempt(user_a, [r1, r2], title=f"Rev {i}", slot_start=start, slot_end=end),
                _attempt(user_b, [r2, r1], title=f"Rev {i}", slot_start=start, slot_end=end),
            )
            assert ok_a != ok_b, (
                f"итерация {i}: ровно один победитель expected, got a={ok_a} b={ok_b}"
            )
