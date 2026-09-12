"""Unit-тесты для ``app.api.users.staff_service.apply_staff_order``.

Контракты:
1. **Дедуп департаментов** — trim + игнор пустых, с сохранением первого вхождения
   (case-sensitive, т.к. дедуп идёт по точной строке после trim).
2. **Дедуп пользователей** — по ``id`` (повторные ``StaffOrderUserItem`` с тем же
   id отбрасываются, остаётся первый).
3. **Дедуп hidden_user_ids** — повторные UUID отбрасываются.
4. **Порядок вызовов репозитория** — ``replace_department_order`` →
   ``apply_user_sort_orders`` → ``apply_hidden_user_ids`` → ``commit``.
5. **Rollback-контракт** — при исключении в любом из репо-методов вызывается
   ``rollback`` и исключение прокидывается выше.
6. **Возврат** — после коммита сервис перечитывает состояние через
   ``fetch_department_order`` + ``fetch_hidden_user_ids`` (read-after-write).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.users.staff_service import apply_staff_order
from app.schemas.user import StaffOrderUpdate, StaffOrderUserItem


@pytest.fixture
def _patched_repo():
    """Патчит все репо-функции, вызываемые сервисом, и возвращает словарь моков."""
    mocks = {
        "replace_department_order": AsyncMock(),
        "apply_user_sort_orders": AsyncMock(),
        "apply_hidden_user_ids": AsyncMock(),
        "fetch_department_order": AsyncMock(return_value=["IT", "HR"]),
        "fetch_hidden_user_ids": AsyncMock(return_value=[]),
    }
    with (
        patch(
            "app.api.users.staff_service.users_repo.replace_department_order",
            mocks["replace_department_order"],
        ),
        patch(
            "app.api.users.staff_service.users_repo.apply_user_sort_orders",
            mocks["apply_user_sort_orders"],
        ),
        patch(
            "app.api.users.staff_service.users_repo.apply_hidden_user_ids",
            mocks["apply_hidden_user_ids"],
        ),
        patch(
            "app.api.users.staff_service.users_repo.fetch_department_order",
            mocks["fetch_department_order"],
        ),
        patch(
            "app.api.users.staff_service.users_repo.fetch_hidden_user_ids",
            mocks["fetch_hidden_user_ids"],
        ),
    ):
        yield mocks


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ── дедуп департаментов ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_departments_dedup_with_trim_and_empty_filter(_patched_repo):
    """Департаменты: trim'ятся, пустые и дубликаты после trim отбрасываются.
    Порядок первого вхождения сохраняется."""
    db = _make_db()
    body = StaffOrderUpdate(
        departments=["  IT  ", "", "HR", "IT", "   ", "Sales"],
        users=[],
        hidden_user_ids=[],
    )

    await apply_staff_order(db, body)

    _patched_repo["replace_department_order"].assert_awaited_once_with(db, ["IT", "HR", "Sales"])


@pytest.mark.asyncio
async def test_departments_all_empty_results_in_empty_list(_patched_repo):
    db = _make_db()
    body = StaffOrderUpdate(departments=["", "  ", "   "])

    await apply_staff_order(db, body)

    _patched_repo["replace_department_order"].assert_awaited_once_with(db, [])


# ── дедуп пользователей ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_users_dedup_by_id_first_wins(_patched_repo):
    """Повторный ``StaffOrderUserItem`` с тем же id отбрасывается. Остаются пары
    (id, sort_order) в порядке первого вхождения."""
    db = _make_db()
    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    body = StaffOrderUpdate(
        users=[
            StaffOrderUserItem(id=uid_a, sort_order=1),
            StaffOrderUserItem(id=uid_b, sort_order=2),
            StaffOrderUserItem(id=uid_a, sort_order=99),  # дубль → отбрасывается
        ]
    )

    await apply_staff_order(db, body)

    _patched_repo["apply_user_sort_orders"].assert_awaited_once_with(db, [(uid_a, 1), (uid_b, 2)])


# ── дедуп hidden_user_ids ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hidden_user_ids_dedup(_patched_repo):
    db = _make_db()
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    body = StaffOrderUpdate(hidden_user_ids=[uid1, uid2, uid1])

    await apply_staff_order(db, body)

    _patched_repo["apply_hidden_user_ids"].assert_awaited_once_with(db, [uid1, uid2])


# ── порядок репо-вызовов + commit ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline_commit_and_readback(_patched_repo):
    """Happy path: все три мутации → commit → перечитывание → StaffOrderState."""
    db = _make_db()
    _patched_repo["fetch_department_order"].return_value = ["IT", "HR"]
    _patched_repo["fetch_hidden_user_ids"].return_value = [uuid.UUID(int=1)]

    uid = uuid.uuid4()
    body = StaffOrderUpdate(
        departments=["IT"],
        users=[StaffOrderUserItem(id=uid, sort_order=5)],
        hidden_user_ids=[uid],
    )

    result = await apply_staff_order(db, body)

    # commit ровно один раз, rollback не вызывался
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()

    # read-back вернул то, что дали fetch_* — сервис это пробрасывает в state
    assert result.departments == ["IT", "HR"]
    assert result.hidden_user_ids == [uuid.UUID(int=1)]


@pytest.mark.asyncio
async def test_repo_call_order(_patched_repo):
    """Гарантирует порядок: replace_department_order → apply_user_sort_orders →
    apply_hidden_user_ids → commit → fetch_department_order → fetch_hidden_user_ids.
    Без commit до конца мутаций read-after-write сломался бы."""
    db = _make_db()
    body = StaffOrderUpdate(
        departments=["IT"],
        users=[StaffOrderUserItem(id=uuid.uuid4(), sort_order=0)],
        hidden_user_ids=[uuid.uuid4()],
    )

    await apply_staff_order(db, body)

    call_order = []
    for name, mock in _patched_repo.items():
        for _call in mock.await_args_list:
            call_order.append(name)

    # Все три мутации вызваны до fetch_*
    mut_names = ["replace_department_order", "apply_user_sort_orders", "apply_hidden_user_ids"]
    fetch_names = ["fetch_department_order", "fetch_hidden_user_ids"]
    mutations_pos = [call_order.index(n) for n in mut_names]
    fetches_pos = [call_order.index(n) for n in fetch_names]
    assert max(mutations_pos) < min(fetches_pos), (
        f"мутации должны идти до fetch: mutations={mutations_pos}, fetches={fetches_pos}"
    )


# ── rollback-контракт ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rollback_on_repo_exception_re_raises(_patched_repo):
    """Контракт транзакционной дисциплины: при исключении в любой репо-мутации
    сервис вызывает ``rollback`` и прокидывает исключение выше. Защита от регресса
    на «проглатывание» ошибки (когда commit/rollback пропущены)."""
    db = _make_db()
    _patched_repo["apply_user_sort_orders"].side_effect = RuntimeError("db boom")

    body = StaffOrderUpdate(users=[StaffOrderUserItem(id=uuid.uuid4(), sort_order=0)])

    with pytest.raises(RuntimeError, match="db boom"):
        await apply_staff_order(db, body)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    # fetch_* не должны вызваться после rollback
    _patched_repo["fetch_department_order"].assert_not_awaited()
    _patched_repo["fetch_hidden_user_ids"].assert_not_awaited()


@pytest.mark.asyncio
async def test_rollback_on_replace_department_order_exception(_patched_repo):
    """Та же защита для первой мутации в цепочке."""
    db = _make_db()
    _patched_repo["replace_department_order"].side_effect = ValueError("bad dept")

    with pytest.raises(ValueError, match="bad dept"):
        await apply_staff_order(db, StaffOrderUpdate(departments=["IT"]))

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


# ── пустой body ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_body_still_commits_and_reads_back(_patched_repo):
    """Пустой StaffOrderUpdate — валидный сценарий (сброс всего).
    Все три мутации вызываются с пустыми списками, commit выполняется, fetch_*
    возвращают актуальное состояние БД (возможно пустое)."""
    db = _make_db()
    _patched_repo["fetch_department_order"].return_value = []
    _patched_repo["fetch_hidden_user_ids"].return_value = []

    result = await apply_staff_order(db, StaffOrderUpdate())

    db.commit.assert_awaited_once()
    _patched_repo["replace_department_order"].assert_awaited_once_with(db, [])
    _patched_repo["apply_user_sort_orders"].assert_awaited_once_with(db, [])
    _patched_repo["apply_hidden_user_ids"].assert_awaited_once_with(db, [])
    assert result.departments == []
    assert result.hidden_user_ids == []
