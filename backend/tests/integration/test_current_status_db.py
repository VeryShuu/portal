"""Integration-тесты пересчёта ``users.current_status`` из ``erp_absences``.

Покрытие:
- активная absence → корректная категория (vacation/sick/business_trip)
- приоритет при пересечении нескольких одновременных отсутствий (sick > vacation > business_trip)
- исчезновение absence → reset_users_to_working сбрасывает в working
- scoped-пересчёт (только затронутые user_ids)
- прошлые absence (end < today) не влияют на статус

Требует INTEGRATION_DB=true (testcontainers, реальная БД).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.erp_sync import ErpAbsence
from app.models.user import User
from app.services.erp_sync.absences_status import (
    recompute_current_status,
    reset_users_to_working,
)

pytestmark = pytest.mark.asyncio


async def _create_user(session, **overrides) -> User:
    defaults = dict(
        email=f"cs-{uuid.uuid4().hex[:8]}@portal.local",
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
    kind: str,
    start: date,
    end: date,
) -> ErpAbsence:
    absence = ErpAbsence(
        user_id=user_id,
        kind=kind,
        start_date=start,
        end_date=end,
        source="erp_sync",
    )
    session.add(absence)
    await session.flush()
    return absence


async def _reload(session, user: User) -> User:
    await session.refresh(user)
    return user


async def test_active_vacation_sets_vacation_status(real_db_session):
    """Активный отпуск → current_status='vacation', until=end_date."""
    user = await _create_user(real_db_session)
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="vacation_main",
        start=today - timedelta(days=2),
        end=today + timedelta(days=5),
    )
    await recompute_current_status(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "vacation"
    assert refreshed.current_status_until == today + timedelta(days=5)


async def test_sick_beats_business_trip_and_vacation(real_db_session):
    """sick > vacation > business_trip: при пересечении нескольких активных
    отсутствий выбирается приоритетная категория (sick)."""
    user = await _create_user(real_db_session)
    today = date.today()
    for kind in ("business_trip", "vacation_main", "sick"):
        await _create_absence(
            real_db_session,
            user_id=user.id,
            kind=kind,
            start=today - timedelta(days=1),
            end=today + timedelta(days=3),
        )
    await recompute_current_status(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "sick"


async def test_vacation_beats_business_trip(real_db_session):
    """vacation > business_trip: одновременно отпуск и командировка → vacation."""
    user = await _create_user(real_db_session)
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="business_trip",
        start=today,
        end=today + timedelta(days=2),
    )
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="day_off_paid",
        start=today,
        end=today + timedelta(days=2),
    )
    await recompute_current_status(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "vacation"


async def test_reset_to_working_when_absence_gone(real_db_session):
    """reset_users_to_working: пользователь без активной absence → working.
    Симулирует исчезновение сотрудника из ERP-отчёта (full-replace)."""
    user = await _create_user(real_db_session, current_status="vacation")
    # ВАЖНО: absence нет — пользователь «потерял» absence, но current_status ещё
    # устаревший. reset должен его вернуть в working.
    await reset_users_to_working(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "working"
    assert refreshed.current_status_until is None


async def test_reset_keeps_user_with_active_absence(real_db_session):
    """reset_users_to_working НЕ трогает пользователя с активной absence."""
    user = await _create_user(real_db_session, current_status="sick")
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="sick",
        start=today,
        end=today + timedelta(days=2),
    )
    await reset_users_to_working(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "sick"


async def test_past_absence_does_not_affect_status(real_db_session):
    """Прошедшая absence (end < today) не должна давать статус — пользователь working."""
    user = await _create_user(real_db_session)
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="vacation_main",
        start=today - timedelta(days=20),
        end=today - timedelta(days=10),
    )
    await recompute_current_status(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "working"
    assert refreshed.current_status_until is None


async def test_scoped_recompute_does_not_touch_other_users(real_db_session):
    """Пересчёт только затронутых user_ids не меняет статус других пользователей."""
    user_in_scope = await _create_user(real_db_session)
    user_out_of_scope = await _create_user(real_db_session, current_status="vacation")
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user_in_scope.id,
        kind="sick",
        start=today,
        end=today + timedelta(days=2),
    )
    # Пересчёт только user_in_scope — user_out_of_scope остаётся 'vacation'
    # (хоть и без absence в БД — scoped-режим не должен его сбрасывать).
    await recompute_current_status(real_db_session, [user_in_scope.id])
    await real_db_session.flush()
    in_scope = await _reload(real_db_session, user_in_scope)
    out_of_scope = await _reload(real_db_session, user_out_of_scope)
    assert in_scope.current_status == "sick"
    assert out_of_scope.current_status == "vacation"  # не тронут


async def test_business_trip_category(real_db_session):
    """Командировка → current_status='business_trip'."""
    user = await _create_user(real_db_session)
    today = date.today()
    await _create_absence(
        real_db_session,
        user_id=user.id,
        kind="business_trip",
        start=today,
        end=today + timedelta(days=3),
    )
    await recompute_current_status(real_db_session, [user.id])
    await real_db_session.flush()
    refreshed = await _reload(real_db_session, user)
    assert refreshed.current_status == "business_trip"
