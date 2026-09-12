"""Unit-тесты для ``app.services.helpdesk.archive_partitions``.

Аналог ``test_audit_partitions.py`` для helpdesk-архива. Контракты:
* ``ensure_helpdesk_archive_partitions`` создаёт партиции на ``months_ahead + 1``
  месяцев вперёд, начиная с текущего месяца (включительно).
* Партиции, уже существующие в ``pg_class`` (``fetchval=True``), пропускаются.
* Возвращается список имён только **созданных** партиций (не пропущенных).
* Формат имени: ``helpdesk_tickets_archive_YYYY_MM``.
* ``CREATE TABLE ... PARTITION OF ... FOR VALUES FROM (...) TO (...)`` —
  интервал полуоткрытый [start, end), где end = start + 1 месяц.

Замораживаем ``datetime.now(tz=UTC)`` через ``patch`` для детерминизма.
Стиль: см. ``test_audit_partitions.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.helpdesk.archive_partitions import (
    ARCHIVE_TABLE,
    ensure_helpdesk_archive_partitions,
)


def _partition_name(year: int, month: int) -> str:
    return f"{ARCHIVE_TABLE}_{year:04d}_{month:02d}"


def _patch_datetime(year: int, month: int):
    """Возвращает ``patch``-объект для ``datetime`` в тестируемом модуле.

    Использовать::

        with _patch_datetime(2026, 4) as mock_dt:
            ...

    Внутри контекста ``datetime.now(tz=UTC)`` вернёт ``datetime(year, month, 1)``.
    ``side_effect`` позволяет остальному коду создавать обычные datetime.
    """
    return patch("app.services.helpdesk.archive_partitions.datetime")


def _configure_mock_dt(mock_dt, *, year: int, month: int) -> None:
    mock_dt.now.return_value = datetime(year, month, 1, tzinfo=UTC)
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)


@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=False)  # партиция не существует
    conn.execute = AsyncMock(return_value=None)
    return conn


# ── контракт: имена партиций + количество ──────────────────────────────────


@pytest.mark.asyncio
async def test_creates_partitions_for_months_ahead(mock_conn):
    """months_ahead=2 → 3 партиции (текущий + 2 следующих)."""
    with _patch_datetime(2026, 4) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=4)
        created = await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=2)

    assert created == [
        _partition_name(2026, 4),
        _partition_name(2026, 5),
        _partition_name(2026, 6),
    ]
    assert mock_conn.execute.await_count == 3


@pytest.mark.asyncio
async def test_creates_partitions_zero_months_ahead(mock_conn):
    """months_ahead=0 → ровно 1 партиция (текущий месяц)."""
    with _patch_datetime(2026, 1) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=1)
        created = await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=0)

    assert created == [_partition_name(2026, 1)]
    mock_conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_months_ahead_is_3(mock_conn):
    """Контракт дефолта: months_ahead=3 → 4 партиции (текущий + 3 следующих)."""
    with _patch_datetime(2026, 12) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=12)
        created = await ensure_helpdesk_archive_partitions(mock_conn)

    assert created == [
        _partition_name(2026, 12),
        _partition_name(2027, 1),  # переход через год
        _partition_name(2027, 2),
        _partition_name(2027, 3),
    ]


@pytest.mark.asyncio
async def test_year_rollover_in_partition_names(mock_conn):
    """Декабрь + months_ahead=2 → декабрь-2026, январь-2027, февраль-2027.
    Регрессия: ``strftime('%Y_%m')`` должен корректно работать для次年."""
    with _patch_datetime(2026, 12) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=12)
        created = await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=2)

    assert created[-1] == _partition_name(2027, 2)


# ── контракт: skip существующих ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skips_existing_partitions(mock_conn):
    """Партиции с ``fetchval=True`` пропускаются (не создаются, не попадают в
    возвращаемый список). Контракт идемпотентности: повторный запуск не делает
    лишних CREATE и не падает на существующих партициях."""
    mock_conn.fetchval = AsyncMock(side_effect=[True, False, True])

    with _patch_datetime(2026, 4) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=4)
        created = await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=2)

    # Создана только партиция за май (средняя из трёх).
    assert created == [_partition_name(2026, 5)]
    mock_conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_existing_returns_empty_list(mock_conn):
    """Все партиции уже есть → возвращается пустой список, execute не вызывается."""
    mock_conn.fetchval = AsyncMock(return_value=True)

    with _patch_datetime(2026, 4) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=4)
        created = await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=2)

    assert created == []
    mock_conn.execute.assert_not_awaited()


# ── контракт: SQL-форма CREATE ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_statement_uses_partition_of_with_range(mock_conn):
    """CREATE TABLE ... PARTITION OF helpdesk_tickets_archive FOR VALUES FROM
    ('YYYY-MM-01') TO ('YYYY-MM-01' следующего месяца). Полуоткрытый интервал."""
    with _patch_datetime(2026, 4) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=4)
        await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=0)

    sql_arg = mock_conn.execute.await_args.args[0]
    assert f"CREATE TABLE IF NOT EXISTS {_partition_name(2026, 4)}" in sql_arg
    assert f"PARTITION OF {ARCHIVE_TABLE}" in sql_arg
    assert "FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')" in sql_arg


@pytest.mark.asyncio
async def test_fetchval_uses_pg_class_query(mock_conn):
    """Контракт проверки существования: SELECT EXISTS через pg_class + pg_namespace
    (public-схема), параметризованный именем таблицы ($1)."""
    with _patch_datetime(2026, 4) as mock_dt:
        _configure_mock_dt(mock_dt, year=2026, month=4)
        await ensure_helpdesk_archive_partitions(mock_conn, months_ahead=0)

    fetchval_args = mock_conn.fetchval.await_args
    sql = fetchval_args.args[0]
    table_name_param = fetchval_args.args[1]

    assert "pg_class" in sql
    assert "pg_namespace" in sql
    assert "nspname = 'public'" in sql
    assert "$1" in sql
    assert table_name_param == _partition_name(2026, 4)
