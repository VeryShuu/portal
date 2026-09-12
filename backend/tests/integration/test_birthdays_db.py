"""Integration-тесты ``users_repo.list_birthdays`` — именинники недели.

Покрытие:
- фильтр по (month, day): только те, чей день рождения попадает в [week_start, week_end]
- переход через Новый год (неделя 29.12–04.01)
- 29 февраля в невисокосной неделе корректно обрабатывается (просто не совпадает)
- сортировка хронологически (month, day, full_name)
- исключаются deleted и staff_hidden
- отсутствие birth_date → исключается

Требует INTEGRATION_DB=true (testcontainers).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.api.users import users_repo
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create(session, **overrides) -> User:
    defaults = dict(
        email=f"bd-{uuid.uuid4().hex[:8]}@portal.local",
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


def _names(users: list[User]) -> list[str]:
    return [u.full_name for u in users]


# ── базовый фильтр недели ───────────────────────────────────────────────────


async def test_returns_only_birthday_people_in_range(real_db_session):
    """Возвращает только тех, чей ДР попадает в неделю (по month/day)."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 3, 9)  # понедельник
    week_end = date(2026, 3, 15)  # воскресенье

    inside_a = await _create(
        real_db_session, full_name=f"InA {marker}", birth_date=date(1990, 3, 10)
    )
    inside_b = await _create(
        real_db_session, full_name=f"InB {marker}", birth_date=date(1985, 3, 15)
    )
    outside_before = await _create(
        real_db_session, full_name=f"OutBefore {marker}", birth_date=date(1990, 3, 8)
    )
    outside_after = await _create(
        real_db_session, full_name=f"After {marker}", birth_date=date(1990, 3, 16)
    )
    other_month = await _create(
        real_db_session, full_name=f"Other {marker}", birth_date=date(1990, 4, 10)
    )
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = [u for u in result if marker in u.full_name]
    assert sorted(_names(related)) == sorted([inside_a.full_name, inside_b.full_name])
    # точно не должно быть вне диапазона
    assert outside_before.full_name not in _names(related)
    assert outside_after.full_name not in _names(related)
    assert other_month.full_name not in _names(related)


async def test_sorting_chronological_by_month_day(real_db_session):
    """Сортировка: хронологически по абсолютной дате, затем ФИО."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 3, 9)
    week_end = date(2026, 3, 15)

    await _create(real_db_session, full_name=f"Zeta {marker}", birth_date=date(1990, 3, 15))
    await _create(real_db_session, full_name=f"Alpha {marker}", birth_date=date(1990, 3, 15))
    await _create(real_db_session, full_name=f"Mid {marker}", birth_date=date(1990, 3, 12))
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = [u.full_name for u in result if marker in u.full_name]
    # 12-е раньше 15-х, а среди 15-х — по алфавиту ФИО
    assert related == [f"Mid {marker}", f"Alpha {marker}", f"Zeta {marker}"]


async def test_sorting_across_month_boundary(real_db_session):
    """Диапазон через границу месяца (конец янв + начало фев): хронологический
    порядок по абсолютной дате, а не по (month, day). 30 янв идёт раньше 1 фев."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 1, 26)  # понедельник
    week_end = date(2026, 2, 8)  # воскресенье (2 недели)

    await _create(real_db_session, full_name=f"Feb1 {marker}", birth_date=date(1990, 2, 1))
    await _create(real_db_session, full_name=f"Jan30 {marker}", birth_date=date(1990, 1, 30))
    await _create(real_db_session, full_name=f"Feb5 {marker}", birth_date=date(1990, 2, 5))
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = [u.full_name for u in result if marker in u.full_name]
    # Абсолютный порядок: 30.01 → 01.02 → 05.02
    assert related == [f"Jan30 {marker}", f"Feb1 {marker}", f"Feb5 {marker}"]


# ── edge-cases ──────────────────────────────────────────────────────────────


async def test_new_year_boundary_week(real_db_session):
    """Неделя через Новый год (29.12–04.01): совпадения и в декабре, и в январе."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2024, 12, 30)  # понедельник
    week_end = date(2025, 1, 5)  # воскресенье

    await _create(real_db_session, full_name=f"Dec {marker}", birth_date=date(1990, 12, 31))
    await _create(real_db_session, full_name=f"Jan {marker}", birth_date=date(1990, 1, 1))
    await _create(real_db_session, full_name=f"JanLate {marker}", birth_date=date(1990, 1, 5))
    await _create(real_db_session, full_name=f"OutDec {marker}", birth_date=date(1990, 12, 28))
    await _create(real_db_session, full_name=f"OutJan {marker}", birth_date=date(1990, 1, 6))
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = _names([u for u in result if marker in u.full_name])
    assert sorted(related) == sorted([f"Dec {marker}", f"Jan {marker}", f"JanLate {marker}"])


async def test_excludes_deleted_and_hidden(real_db_session):
    """Исключает удалённых и скрытых сотрудников."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 3, 9)
    week_end = date(2026, 3, 15)

    visible = await _create(
        real_db_session, full_name=f"Visible {marker}", birth_date=date(1990, 3, 10)
    )
    hidden = await _create(
        real_db_session,
        full_name=f"Hidden {marker}",
        birth_date=date(1990, 3, 11),
        staff_hidden=True,
    )
    deleted = await _create(
        real_db_session,
        full_name=f"Deleted {marker}",
        birth_date=date(1990, 3, 12),
        deleted_at=datetime.now(UTC),
    )
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = _names([u for u in result if marker in u.full_name])
    assert related == [visible.full_name]
    assert hidden.full_name not in related
    assert deleted.full_name not in related


async def test_excludes_users_without_birth_date(real_db_session):
    """Пользователи без birth_date не возвращаются."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 3, 9)
    week_end = date(2026, 3, 15)

    await _create(real_db_session, full_name=f"NoBd {marker}", birth_date=None)
    with_bd = await _create(
        real_db_session, full_name=f"WithBd {marker}", birth_date=date(1990, 3, 10)
    )
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    related = _names([u for u in result if marker in u.full_name])
    assert related == [with_bd.full_name]


async def test_empty_week_returns_empty(real_db_session):
    """Если в неделе ни одного ДР — пустой список."""
    marker = uuid.uuid4().hex[:6]
    week_start = date(2026, 3, 9)
    week_end = date(2026, 3, 15)

    await _create(real_db_session, full_name=f"Other {marker}", birth_date=date(1990, 5, 20))
    await real_db_session.flush()

    result = await users_repo.list_birthdays(
        real_db_session, week_start=week_start, week_end=week_end
    )
    assert [u for u in result if marker in u.full_name] == []
