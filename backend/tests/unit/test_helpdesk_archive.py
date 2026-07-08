"""Unit-тесты для archive-сервиса helpdesk.

Фокус — транзакционная дисциплина: ``archive_closed_tickets`` ДОЛЖЕН вызывать
``db.commit()`` (раньше делал только ``flush``, что в проде с ``autocommit=False``
приводило к silent no-op — архивные строки откатывались на выходе из сессии).

Интеграционный тест ``test_helpdesk_ingress.py::TestArchive`` читает результат
в той же savepoint-сессии сразу после flush и потому маскирует отсутствие commit.
Здесь — мок-сессия с ``commit.assert_awaited_*``, паттерн ``test_audit``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.constants import HELPDESK_ARCHIVE_AFTER_DAYS
from app.services.helpdesk.archive import archive_closed_tickets


def _make_ticket_row(*, number: int = 1, subject: str = "S") -> SimpleNamespace:
    old = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_AFTER_DAYS + 5)
    return SimpleNamespace(
        id=MagicMock(),
        number=number,
        subject=subject,
        description="d",
        status="closed",
        source="web",
        requester_email="r@example.com",
        requester_name="R",
        requester_user_id=None,
        assignee_user_id=None,
        created_at=datetime.now(UTC),
        closed_at=old,
        closed_by_user_id=None,
    )


def _make_result(rows: list) -> MagicMock:
    """Имитация ``Result``: ``.scalars().unique().all()`` → rows."""
    scalars = MagicMock()
    scalars.unique.return_value = scalars
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _make_db(ticket_rows: list) -> MagicMock:
    """Мок AsyncSession для archive_closed_tickets.

    Первым ``execute`` (SELECT закрытых тикетов) возвращаем ``ticket_rows``;
    последующие execute (сообщения/вложения каждого тикета) — пустые.
    ``add``/``delete``/``flush``/``commit`` — AsyncMock/MagicMock.
    """
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_make_result(ticket_rows)] + [_make_result([])] * 6)
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_archive_commits_transaction_when_there_are_tickets() -> None:
    """CRITICAL: при наличии архивируемых тикетов сервис обязан вызвать
    ``db.commit()``. Без него архивация — silent no-op (flush откатывается)."""
    db = _make_db([_make_ticket_row(number=101)])

    archived = await archive_closed_tickets(db)

    assert archived == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_does_not_commit_when_nothing_to_archive() -> None:
    """Нет закрытых тикетов → нет commit (соответствует паттерну
    ``auto_close_resolved_tickets``: commit только при наличии изменений)."""
    db = _make_db([])

    archived = await archive_closed_tickets(db)

    assert archived == 0
    db.commit.assert_not_awaited()
