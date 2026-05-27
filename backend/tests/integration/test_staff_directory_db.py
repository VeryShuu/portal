"""Integration-тесты репозиторных функций справочника сотрудников.

Покрытие:
- list_departments      — distinct, без None/пустых, отсортирован
- list_offices          — distinct из attributes->>'office'
- _build_list_conditions — фильтр по office, поиск по position
                          и attributes->>'internal_phone'
- list_users_page       — sort=department использует (department NULLS LAST, full_name)
- stream_users          — асинхронный генератор отдаёт всех отфильтрованных пользователей

Требует INTEGRATION_DB=true.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.api.users import users_repo
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create(session, **overrides) -> User:
    defaults = dict(
        email=f"staff-{uuid.uuid4().hex[:8]}@portal.local",
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


# ── list_departments ────────────────────────────────────────────────────────
async def test_list_departments_returns_sorted_distinct(real_db_session):
    """Возвращает уникальные отделы в алфавитном порядке."""
    marker = uuid.uuid4().hex[:6]
    await _create(real_db_session, full_name=f"A {marker}", department=f"ZZ-{marker}")
    await _create(real_db_session, full_name=f"B {marker}", department=f"AA-{marker}")
    await _create(real_db_session, full_name=f"C {marker}", department=f"AA-{marker}")
    await real_db_session.flush()

    items = await users_repo.list_departments(real_db_session)

    # фильтруем — в БД могут быть данные от других тестов или фикстур
    related = [d for d in items if marker in (d or "")]
    assert related == [f"AA-{marker}", f"ZZ-{marker}"]


async def test_list_departments_excludes_blank_and_null(real_db_session):
    """Пустые и None отделы исключаются из выдачи."""
    marker = uuid.uuid4().hex[:6]
    await _create(real_db_session, full_name=f"X {marker}", department=None)
    await _create(real_db_session, full_name=f"Y {marker}", department="")
    await _create(real_db_session, full_name=f"Z {marker}", department=f"DEPT-{marker}")
    await real_db_session.flush()

    items = await users_repo.list_departments(real_db_session)
    assert f"DEPT-{marker}" in items
    assert "" not in items
    assert None not in items


# ── list_offices ────────────────────────────────────────────────────────────
async def test_list_offices_reads_from_attributes(real_db_session):
    """Берёт уникальные значения из attributes->>'city'."""
    marker = uuid.uuid4().hex[:6]
    await _create(
        real_db_session,
        full_name=f"O1 {marker}",
        attributes={"city": f"Москва-{marker}"},
    )
    await _create(
        real_db_session,
        full_name=f"O2 {marker}",
        attributes={"city": f"Москва-{marker}"},
    )
    await _create(
        real_db_session,
        full_name=f"O3 {marker}",
        attributes={"city": f"Мурманск-{marker}"},
    )
    await _create(real_db_session, full_name=f"O4 {marker}", attributes={})
    await real_db_session.flush()

    items = await users_repo.list_offices(real_db_session)
    related = [o for o in items if marker in (o or "")]
    assert sorted(related) == [f"Москва-{marker}", f"Мурманск-{marker}"]


# ── фильтр office в list_users_page ─────────────────────────────────────────
async def test_list_users_page_filters_by_office(real_db_session):
    marker = uuid.uuid4().hex[:6]
    u1 = await _create(
        real_db_session,
        full_name=f"In office {marker}",
        attributes={"city": f"OF-{marker}"},
    )
    await _create(
        real_db_session,
        full_name=f"Other office {marker}",
        attributes={"city": f"OTHER-{marker}"},
    )
    await real_db_session.flush()

    items = await users_repo.list_users_page(
        real_db_session,
        q=None,
        department=None,
        office=f"OF-{marker}",
        sort="full_name",
        page=1,
        page_size=50,
    )
    ids = [u.id for u in items]
    assert u1.id in ids
    # ровно один из наших — другой office не попал
    assert sum(1 for u in items if marker in (u.full_name or "")) == 1


# ── поиск q расширен на position и internal_phone ──────────────────────────
async def test_search_q_matches_position(real_db_session):
    marker = uuid.uuid4().hex[:6]
    target = await _create(
        real_db_session,
        full_name=f"NoMatch Name {marker}",
        position=f"UniquePos-{marker}",
    )
    await real_db_session.flush()

    items = await users_repo.list_users_page(
        real_db_session,
        q=f"UniquePos-{marker}",
        department=None,
        office=None,
        sort="full_name",
        page=1,
        page_size=10,
    )
    assert any(u.id == target.id for u in items)


async def test_search_q_matches_internal_phone(real_db_session):
    """Поиск по короткому внутреннему номеру (важный сценарий из ТЗ)."""
    marker = uuid.uuid4().hex[:6]
    short_phone = f"312{marker[:3]}"
    target = await _create(
        real_db_session,
        full_name=f"PhoneOwner {marker}",
        attributes={"internal_phone": short_phone},
    )
    await real_db_session.flush()

    items = await users_repo.list_users_page(
        real_db_session,
        q=short_phone,
        department=None,
        office=None,
        sort="full_name",
        page=1,
        page_size=10,
    )
    assert any(u.id == target.id for u in items)


# ── sort=department ─────────────────────────────────────────────────────────
async def test_list_users_page_sort_department(real_db_session):
    """sort=department: department ASC NULLS LAST, затем full_name ASC."""
    marker = uuid.uuid4().hex[:6]
    a = await _create(real_db_session, full_name=f"a-{marker}", department=f"BB-{marker}")
    b = await _create(real_db_session, full_name=f"b-{marker}", department=f"AA-{marker}")
    c = await _create(real_db_session, full_name=f"c-{marker}", department=f"AA-{marker}")
    null_dept = await _create(real_db_session, full_name=f"d-{marker}", department=None)
    await real_db_session.flush()

    items = await users_repo.list_users_page(
        real_db_session,
        q=marker,
        department=None,
        office=None,
        sort="department",
        page=1,
        page_size=50,
    )
    ids = [u.id for u in items]
    # AA-* идут первыми, b раньше c (full_name asc), потом BB-*, NULL в конце
    assert ids.index(b.id) < ids.index(c.id) < ids.index(a.id)
    assert ids.index(a.id) < ids.index(null_dept.id)


# ── stream_users ────────────────────────────────────────────────────────────
async def test_apply_user_sort_orders_batch(real_db_session):
    """apply_user_sort_orders проставляет sort_order одним батчем."""
    marker = uuid.uuid4().hex[:6]
    users = []
    for i in range(5):
        u = await _create(
            real_db_session,
            full_name=f"Batch {marker} {i}",
            department=f"D-{marker}",
        )
        users.append(u)
    await real_db_session.flush()

    items = [(u.id, idx * 10) for idx, u in enumerate(users)]
    await users_repo.apply_user_sort_orders(real_db_session, items)
    await real_db_session.flush()

    for u in users:
        await real_db_session.refresh(u)
    expected = {u.id: idx * 10 for idx, u in enumerate(users)}
    actual = {u.id: u.staff_sort_order for u in users}
    assert actual == expected


async def test_apply_user_sort_orders_resets_when_empty(real_db_session):
    marker = uuid.uuid4().hex[:6]
    u = await _create(
        real_db_session,
        full_name=f"Reset {marker}",
        department=f"D-{marker}",
        staff_sort_order=42,
    )
    await real_db_session.flush()

    await users_repo.apply_user_sort_orders(real_db_session, [])
    await real_db_session.flush()
    await real_db_session.refresh(u)
    assert u.staff_sort_order is None


async def test_apply_user_sort_orders_for_100_users(real_db_session):
    """Корректность батч-UPDATE на 100 пользователях."""
    marker = uuid.uuid4().hex[:6]
    users = []
    for i in range(100):
        u = await _create(
            real_db_session,
            full_name=f"Big {marker} {i:03d}",
            department=f"D-{marker}",
        )
        users.append(u)
    await real_db_session.flush()

    items = [(u.id, i) for i, u in enumerate(users)]
    await users_repo.apply_user_sort_orders(real_db_session, items)
    await real_db_session.flush()

    for u in users:
        await real_db_session.refresh(u)
    assert {u.staff_sort_order for u in users} == set(range(100))


async def test_replace_department_order_and_fetch(real_db_session):
    marker = uuid.uuid4().hex[:6]
    depts = [f"AA-{marker}", f"BB-{marker}", f"CC-{marker}"]
    await users_repo.replace_department_order(real_db_session, depts)
    await real_db_session.flush()

    fetched = await users_repo.fetch_department_order(real_db_session)
    related = [d for d in fetched if marker in d]
    assert related == depts


async def test_apply_hidden_user_ids_resets_when_empty(real_db_session):
    marker = uuid.uuid4().hex[:6]
    u = await _create(
        real_db_session,
        full_name=f"Hidden {marker}",
        department=f"D-{marker}",
        staff_hidden=True,
    )
    await real_db_session.flush()

    await users_repo.apply_hidden_user_ids(real_db_session, [])
    await real_db_session.flush()
    await real_db_session.refresh(u)
    assert u.staff_hidden is False


async def test_apply_hidden_user_ids_sets_only_listed(real_db_session):
    marker = uuid.uuid4().hex[:6]
    u1 = await _create(real_db_session, full_name=f"H1 {marker}")
    u2 = await _create(real_db_session, full_name=f"H2 {marker}")
    u3 = await _create(real_db_session, full_name=f"H3 {marker}")
    await real_db_session.flush()

    await users_repo.apply_hidden_user_ids(real_db_session, [u1.id, u3.id])
    await real_db_session.flush()
    for u in (u1, u2, u3):
        await real_db_session.refresh(u)
    assert u1.staff_hidden is True
    assert u2.staff_hidden is False
    assert u3.staff_hidden is True


async def test_stream_users_yields_all_with_filters(real_db_session):
    """Async-генератор отдаёт всех отфильтрованных пользователей."""
    marker = uuid.uuid4().hex[:6]
    for i in range(5):
        await _create(
            real_db_session,
            full_name=f"Stream {marker} {i}",
            department=f"DEPT-{marker}",
        )
    await _create(
        real_db_session,
        full_name=f"Other {marker}",
        department=f"OTHER-{marker}",
    )
    await real_db_session.flush()

    collected = []
    async for u in users_repo.stream_users(
        real_db_session,
        q=None,
        department=f"DEPT-{marker}",
        office=None,
        sort="full_name",
    ):
        collected.append(u)

    assert len(collected) == 5
    assert all(u.department == f"DEPT-{marker}" for u in collected)
