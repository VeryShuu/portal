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

import unittest.mock
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.helpdesk import HelpdeskVisibility, MessageCreateIn
from app.services.helpdesk.messages import (
    add_agent_reply,
    add_requester_reply,
    fetch_ticket_with_messages,
)
from app.services.helpdesk.tickets import assign_ticket


def _ticket(*, status: str = "new", number: int = 5) -> Any:
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


def _user(*, uid: str = "user-uuid", email: str = "agent@example.com") -> Any:
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
        payload=MessageCreateIn(body_text="ответ", visibility=HelpdeskVisibility("public")),
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
        payload=MessageCreateIn(body_text="заметка", visibility=HelpdeskVisibility("internal")),
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


# ---------------------------------------------------------------------------
# add_requester_reply — ответ инициатора (inbound/public, reopen-логика).
# В отличие от add_agent_reply, сервис САМ делает commit (роутер не ставит
# outbox-запись на ответ инициатора — письмо уходит только агентам через
# notify_*; здесь же просто фиксируется новое сообщение).
# ---------------------------------------------------------------------------


def _make_db_with_message(*, attachments: list | None = None) -> MagicMock:
    """Мок AsyncSession, где ``_eager_load_attachments`` находит сообщение.

    В отличие от ``_make_db`` (возвращает ``None`` из ``one_or_none``), этот
    мок возвращает ``fresh`` с ``.attachments`` — покрывает ветку
    ``fresh is not None`` в ``_eager_load_attachments``."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    fresh = SimpleNamespace(attachments=attachments or [])
    result = MagicMock()
    result.scalars.return_value.unique.return_value.one_or_none.return_value = fresh
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_add_requester_reply_commits_and_forces_inbound_public() -> None:
    """Ответ инициатора всегда inbound/public (независимо от payload) и
    коммитится сервисом. ``new`` не реопенится."""
    db = _make_db_with_message()
    ticket = _ticket(status="new")
    user = _user()

    msg = await add_requester_reply(
        db,
        ticket=ticket,
        user=user,
        payload=MessageCreateIn(body_text="ответ заявителя"),
        files=None,
    )

    db.commit.assert_awaited()
    db.flush.assert_awaited()
    db.refresh.assert_awaited()
    assert ticket.status == "new"  # new не входит в _REQUESTER_REOPEN_STATUSES
    assert ticket.last_activity_at is not None
    assert msg.direction == "inbound"
    assert msg.visibility == "public"
    assert msg.source == "web"
    assert msg.author_user_id == user.id


@pytest.mark.parametrize("status", ["pending"])
@pytest.mark.asyncio
async def test_add_requester_reply_reopens_pending(status: str) -> None:
    """ТЗ §4.2.1: ответ клиента из ``pending`` → ``open`` (клиент «проснулся»).
    ``resolved`` упразднён (079) — reopen из ``closed`` идёт через отдельный
    путь с окном HELPDESK_REOPEN_WINDOW_DAYS."""
    db = _make_db_with_message()
    ticket = _ticket(status=status)
    user = _user()

    await add_requester_reply(
        db,
        ticket=ticket,
        user=user,
        payload=MessageCreateIn(body_text="дополнение"),
    )

    assert ticket.status == "open"


@pytest.mark.asyncio
async def test_add_requester_reply_uploads_files_when_provided() -> None:
    """``files`` триггерит ``upload_attachments`` (импорт внутри функции)."""
    db = _make_db_with_message()
    ticket = _ticket(status="open")
    user = _user()

    with unittest.mock.patch(
        "app.services.helpdesk.attachments.upload_attachments",
        new=AsyncMock(),
    ) as uploaded:
        await add_requester_reply(
            db,
            ticket=ticket,
            user=user,
            payload=MessageCreateIn(body_text="с вложением"),
            files=[SimpleNamespace(filename="x.png")],
        )

    uploaded.assert_awaited_once()
    # Аргументы: db, ticket, message_id, files, actor.
    assert uploaded.await_args is not None
    _call_kwargs = uploaded.await_args.kwargs
    assert _call_kwargs["ticket"] is ticket
    assert _call_kwargs["actor"] is user


@pytest.mark.asyncio
async def test_add_requester_reply_eager_loads_attachments() -> None:
    """``_eager_load_attachments`` копирует ``fresh.attachments`` на сообщение
    (ветка ``fresh is not None``). ``attachments`` реального HelpdeskMessage
    требует ORM-совместимые элементы, поэтому здесь — пустой список (проверка
    ветки ``fresh is not None`` и факта присваивания; содержимое покрывается
    integration-тестами с реальной БД)."""
    db = _make_db_with_message(attachments=[])
    ticket = _ticket(status="open")
    user = _user()

    msg = await add_requester_reply(
        db,
        ticket=ticket,
        user=user,
        payload=MessageCreateIn(body_text="текст"),
    )

    # execute вызван дважды: upload_attachments нет (files=None),
    # остаётся один вызов _eager_load_attachments.
    assert db.execute.await_count >= 1
    assert msg is not None
    # fresh.attachments (пустой список) присвоен на сообщение без ошибки.
    assert msg.attachments == []


# ---------------------------------------------------------------------------
# fetch_ticket_with_messages — загрузка тикета с тредом для роутера.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_ticket_with_messages_returns_ticket() -> None:
    """Возвращает тикет с eager-loaded messages (используется роутером после
    добавления ответа для возврата обновлённого таймлайна)."""
    ticket_id = uuid.uuid4()
    expected = SimpleNamespace(id=ticket_id, messages=[])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.one_or_none.return_value = expected
    db.execute = AsyncMock(return_value=result)

    got = await fetch_ticket_with_messages(db, ticket_id=ticket_id)

    assert got is expected
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_ticket_with_messages_returns_none_when_missing() -> None:
    """Тикет не найден → None (роутер сам бросит 404)."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    got = await fetch_ticket_with_messages(db, ticket_id=uuid.uuid4())

    assert got is None
