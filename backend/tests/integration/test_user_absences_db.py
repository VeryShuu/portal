"""Integration-тесты ``users_repo.list_user_absences`` — отсутствия в профиле.

Покрытие:
- фильтр ``end_date >= today``: актуальные и будущие, НЕ прошедшие
- сортировка по ``start_date`` ASC (ближайшие первыми)
- изолированность по ``user_id`` (чужие отсутствия не возвращаются)
- пустой результат для пользователя без отсутствий

Требует INTEGRATION_DB=true (testcontainers).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.users import users_repo
from app.models.erp_sync import ErpAbsence
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(session, **overrides) -> User:
    defaults = dict(
        email=f"abs-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Test User",
        role="reader",
        auth_source="local",
        presence_status="office",
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
    position: str | None = "Инженер",
    department: str | None = "Отдел",
) -> ErpAbsence:
    absence = ErpAbsence(
        user_id=user_id,
        kind=kind,
        position=position,
        department=department,
        start_date=start,
        end_date=end,
        source="erp_sync",
    )
    session.add(absence)
    await session.flush()
    return absence


async def test_returns_only_current_and_future(real_db_session):
    """Возвращает только ``end_date >= today`` (актуальные/будущие), не прошедшие."""
    user = await _create_user(real_db_session)
    today = date.today()

    # Прошедший отпуск (end < today) — НЕ возвращается.
    await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today - timedelta(days=20),
        end=today - timedelta(days=10),
    )
    # Текущий отпуск (today внутри диапазона) — возвращается.
    current = await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today - timedelta(days=2),
        end=today + timedelta(days=5),
    )
    # Будущий отпуск — возвращается.
    future = await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today + timedelta(days=30),
        end=today + timedelta(days=40),
    )

    result = await users_repo.list_user_absences(real_db_session, user_id=user.id)
    ids = [a.id for a in result]
    assert current.id in ids
    assert future.id in ids
    assert len(result) == 2  # прошедший исключён


async def test_sorted_by_start_date_asc(real_db_session):
    """Сортировка по ``start_date`` ASC — ближайшие отсутствия первыми."""
    user = await _create_user(real_db_session)
    today = date.today()

    # Создаём в «непоследовательном» порядке — сортировка должна выстроить по дате.
    far = await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today + timedelta(days=60),
        end=today + timedelta(days=70),
    )
    near = await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today + timedelta(days=5),
        end=today + timedelta(days=10),
    )
    mid = await _create_absence(
        real_db_session,
        user_id=user.id,
        start=today + timedelta(days=20),
        end=today + timedelta(days=25),
    )

    result = await users_repo.list_user_absences(real_db_session, user_id=user.id)
    assert [a.start_date for a in result] == [near.start_date, mid.start_date, far.start_date]


async def test_isolated_by_user_id(real_db_session):
    """Чужие отсутствия не возвращаются — только запрошенного пользователя."""
    user_a = await _create_user(real_db_session, full_name="User A")
    user_b = await _create_user(real_db_session, full_name="User B")
    today = date.today()

    await _create_absence(real_db_session, user_id=user_a.id, start=today, end=today)
    await _create_absence(
        real_db_session, user_id=user_b.id, start=today, end=today, position="Другая должность"
    )

    result_a = await users_repo.list_user_absences(real_db_session, user_id=user_a.id)
    assert len(result_a) == 1
    assert result_a[0].user_id == user_a.id


async def test_empty_for_user_without_absences(real_db_session):
    """Пользователь без отсутствий → пустой список (не None, не ошибка)."""
    user = await _create_user(real_db_session)
    result = await users_repo.list_user_absences(real_db_session, user_id=user.id)
    assert result == []
    assert len(result) == 0


async def test_all_kinds_returned(real_db_session):
    """Все 7 типов отсутствий возвращаются (нет фильтра по kind в READ API)."""
    user = await _create_user(real_db_session)
    today = date.today()
    kinds = [
        "vacation_main",
        "vacation_extra",
        "unpaid_leave",
        "sick",
        "business_trip",
        "day_off_paid",
        "day_off_unpaid",
    ]
    for i, kind in enumerate(kinds):
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind=kind,
            start=today + timedelta(days=i + 1),
            end=today + timedelta(days=i + 2),
        )

    result = await users_repo.list_user_absences(real_db_session, user_id=user.id)
    returned_kinds = sorted(a.kind for a in result)
    assert returned_kinds == sorted(kinds)


async def test_single_day_absence(real_db_session):
    """Однодневный отгул (start == end == today) возвращается (end >= today)."""
    user = await _create_user(real_db_session)
    today = date.today()

    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="day_off_paid",
        start=today,
        end=today,
    )
    result = await users_repo.list_user_absences(real_db_session, user_id=user.id)
    assert len(result) == 1
    assert result[0].start_date == result[0].end_date == today
