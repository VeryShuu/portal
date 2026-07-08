"""Unit-тесты транзакционной дисциплины helpdesk messages / assign.

Контракт (после fixed #3 outbox-инвариант):

* ``add_agent_reply`` НЕ делает ``db.commit()`` — только ``flush``. Caller
  (роутер) обязан поставить outbox-запись в той же транзакции и сделать единый
  ``commit``. Раньше commit был здесь, а outbox — отдельным commit в роутере,
  что нарушало outbox-инвариант AGENTS.md (сбой второго commit терял письмо
  заявителю при сохранённом ответе).

* ``assign_ticket`` НЕ делает ``db.commit()`` — только мутирует объект. Тот же
  инвариант для письма о назначении.

Эти тесты — регрессионная защита: если кто-то вернёт ``commit`` внутрь сервиса,
``assert_not_awaited`` упадёт.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.helpdesk import MessageCreateIn
from app.services.helpdesk.messages import add_agent_reply
from app.services.helpdesk.tickets import assign_ticket


def _ticket(*, status: str = "new", number: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        id="ticket-uuid",
        number=number,
        status=status,
        assignee_user_id=None,
        assigned_at=None,
        closed_at=None,
        closed_by_user_id=None,
        last_activity_at=datetime(2026, 7, 1),
    )


def _user(*, uid: str = "user-uuid", email: str = "agent@example.com") -> SimpleNamespace:
    return SimpleNamespace(id=uid, email=email, full_name="Агент")


def _make_db() -> MagicMock:
    """Мок AsyncSession: ``add``/``flush``/``refresh`` — no-op AsyncMock.
    ``commit`` фиксируется, чтобы утверждать его отсутствие."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    # _eager_load_attachments делает execute → возвращаем пустой результат.
    result = MagicMock()
    result.scalars.return_value.unique.return_value.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_add_agent_reply_does_not_commit() -> None:
    """Контракт outbox-инварианта: сервис не коммитит — роутер делает единый
    commit с outbox-записью. Возврат commit сюда нарушал бы атомарность."""
    db = _make_db()
    ticket = _ticket(status="new")
    agent = _user()

    await add_agent_reply(
        db,
        ticket=ticket,
        agent=agent,
        payload=MessageCreateIn(body_text="ответ", visibility="public"),
        files=[],
        support_domain="example.com",
    )

    db.commit.assert_not_awaited()
    # Но flush — да (нужен message.id для outbox/вложений).
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_add_agent_reply_internal_also_no_commit() -> None:
    """Internal-заметка (без outbox) — тоже без commit в сервисе. Роутер всё
    равно делает единый commit для согласованности контракта."""
    db = _make_db()
    ticket = _ticket(status="open")
    agent = _user()

    await add_agent_reply(
        db,
        ticket=ticket,
        agent=agent,
        payload=MessageCreateIn(body_text="заметка", visibility="internal"),
        files=[],
        support_domain="example.com",
    )

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_ticket_does_not_commit() -> None:
    """Контракт outbox-инварианта: назначение не коммитит — роутер делает
    единый commit с письмом о назначении."""
    db = _make_db()
    ticket = _ticket(status="new")
    assignee = _user(uid="assignee-uuid")

    result = await assign_ticket(db, ticket=ticket, assignee_id=assignee.id)

    db.commit.assert_not_awaited()
    # Мутация применена в памяти (объект возвращён, статус изменён).
    assert result is ticket
    assert ticket.assignee_user_id == assignee.id
    assert ticket.status == "open"  # new → open при назначении
