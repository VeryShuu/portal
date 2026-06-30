"""Integration tests for the requester web-flow of Helpdesk (Этап 2).

Покрывает создание тикета (с инвариантом первого сообщения), списочное чтение
«своих», карточку с публичными сообщениями, ответ инициатора и — главное —
ACL «только свои»: чужой тикет не доступен ни на чтение, ни для ответа.

Стиль — как у ``test_directories_db.py``: функции роутера вызываются напрямую
на SAVEPOINT-изолированной сессии. ``redis`` для этапа 2 не используется
(уведомления появляются на этапе 4), поэтому передаётся mock.

Авто-skip'ается без ``INTEGRATION_DB=true`` (нет реальной PostgreSQL).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.schemas.helpdesk import MessageCreateIn, TicketCreateIn

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    """Mock Redis — на этапе 2 роутер его не трогает, но сигнатура требует."""
    return AsyncMock()


def _payload(subject: str = "Не работает VPN") -> TicketCreateIn:
    return TicketCreateIn(subject=subject, description="Подробности заявки")


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    """Заявка, созданная ``real_user`` (reader) через web-flow."""
    from app.api.helpdesk.tickets import create_ticket

    return await create_ticket(_payload(), real_user, real_db_session, _redis())


@pytest_asyncio.fixture
async def ticket_of_editor(real_db_session, real_editor):
    """Заявка, принадлежащая другому пользователю (editor) — для ACL-проверок."""
    from app.api.helpdesk.tickets import create_ticket

    return await create_ticket(
        TicketCreateIn(subject="Чужая заявка", description="не моя"),
        real_editor,
        real_db_session,
        _redis(),
    )


# ---------------------------------------------------------------------------
# Создание + инвариант первого сообщения
# ---------------------------------------------------------------------------


class TestCreateTicket:
    async def test_creates_with_new_status_and_web_source(self, real_db_session, real_user, ticket):
        assert ticket.status == "new"
        assert ticket.source == "web"
        assert ticket.requester_user_id == real_user.id
        assert ticket.requester_email == real_user.email
        assert ticket.requester_name == real_user.full_name

    async def test_human_readable_number_assigned(self, ticket):
        # IDENTITY-колонка должна быть заполнена.
        assert isinstance(ticket.number, int)
        assert ticket.number > 0

    async def test_first_message_invariant(self, real_db_session, ticket):
        """При создании всегда создаётся первое inbound/public сообщение,
        дублирующее description (ТЗ §4.3.1)."""
        from app.services.helpdesk.tickets import fetch_ticket_for_user

        full = await fetch_ticket_for_user(
            real_db_session, ticket_id=ticket.id, user_id=ticket.requester_user_id
        )
        assert full is not None
        # Публичный таймлайн инициатора содержит ровно одно первое сообщение.
        public = [m for m in full.messages if m.visibility != "internal"]
        assert len(public) == 1
        first = public[0]
        assert first.direction == "inbound"
        assert first.visibility == "public"
        assert first.source == "web"
        assert first.body_text == ticket.description
        assert first.author_user_id == ticket.requester_user_id


# ---------------------------------------------------------------------------
# Список своих
# ---------------------------------------------------------------------------


class TestListMyTickets:
    async def test_only_own_tickets_visible(
        self, real_db_session, real_user, real_editor, ticket, ticket_of_editor
    ):
        from app.services.helpdesk.tickets import count_my_tickets, list_my_tickets

        total = await count_my_tickets(real_db_session, user_id=real_user.id, status_filter=None)
        items = await list_my_tickets(
            real_db_session, user_id=real_user.id, status_filter=None, limit=50, offset=0
        )
        ids = {t.id for t in items}
        assert total == 1
        assert ticket.id in ids
        # Чужая заявка editor'а не видна reader'у.
        assert ticket_of_editor.id not in ids

    async def test_status_filter(self, real_db_session, real_user, ticket):
        from app.services.helpdesk.tickets import count_my_tickets

        assert (
            await count_my_tickets(real_db_session, user_id=real_user.id, status_filter="new") == 1
        )
        assert (
            await count_my_tickets(real_db_session, user_id=real_user.id, status_filter="closed")
            == 0
        )

    async def test_pagination_shape(self, real_db_session, real_user, ticket):
        from app.api.helpdesk.tickets import list_my_tickets

        res = await list_my_tickets(
            real_user,
            real_db_session,
            status_filter=None,
            limit=10,
            offset=0,
        )
        assert res.total == 1
        assert res.limit == 10
        assert res.offset == 0
        assert len(res.items) == 1
        assert res.items[0].id == ticket.id


# ---------------------------------------------------------------------------
# Карточка + ACL
# ---------------------------------------------------------------------------


class TestGetMyTicket:
    async def test_own_ticket_visible(self, real_db_session, real_user, ticket):
        from app.api.helpdesk.tickets import get_my_ticket

        out = await get_my_ticket(ticket.id, real_user, real_db_session)
        assert out.id == ticket.id
        # Публичный таймлайн содержит первое сообщение.
        assert len(out.messages) == 1
        assert out.messages[0].visibility.value == "public"

    async def test_foreign_ticket_returns_404(self, real_db_session, real_user, ticket_of_editor):
        """ACL: чужой тикет = 404 (не раскрываем существование)."""
        from app.api.helpdesk.tickets import get_my_ticket

        with pytest.raises(HTTPException) as exc:
            await get_my_ticket(ticket_of_editor.id, real_user, real_db_session)
        assert exc.value.status_code == 404

    async def test_random_uuid_returns_404(self, real_db_session, real_user):
        from app.api.helpdesk.tickets import get_my_ticket

        with pytest.raises(HTTPException) as exc:
            await get_my_ticket(uuid.uuid4(), real_user, real_db_session)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Ответ инициатора + статус-переходы
# ---------------------------------------------------------------------------


class TestAddRequesterReply:
    async def _set_status(self, db, ticket, status_value: str) -> None:
        """Прямое переключение статуса тикета для проверки переходов (агентских
        endpoints на этапе 2 ещё нет — меняем в БД напрямую)."""
        ticket.status = status_value
        await db.flush()
        await db.refresh(ticket)

    async def test_reply_appended_as_inbound_public(self, real_db_session, real_user, ticket):
        from app.api.helpdesk.tickets import add_my_message

        msg = await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="Дополнение от клиента"),
            real_user,
            real_db_session,
            _redis(),
        )
        assert msg.direction.value == "inbound"
        assert msg.visibility.value == "public"
        assert msg.body_text == "Дополнение от клиента"

    async def test_reply_reopens_pending(self, real_db_session, real_user, ticket):
        from app.api.helpdesk.tickets import add_my_message

        await self._set_status(real_db_session, ticket, "pending")
        await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="ответ"),
            real_user,
            real_db_session,
            _redis(),
        )
        await real_db_session.refresh(ticket)
        assert ticket.status == "open"

    async def test_reply_reopens_resolved_without_window(self, real_db_session, real_user, ticket):
        """ТЗ §4.2: resolved → open по любому ответу клиента, без окна."""
        from app.api.helpdesk.tickets import add_my_message

        await self._set_status(real_db_session, ticket, "resolved")
        await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="не подтверждено"),
            real_user,
            real_db_session,
            _redis(),
        )
        await real_db_session.refresh(ticket)
        assert ticket.status == "open"

    async def test_reply_updates_last_activity(self, real_db_session, real_user, ticket):
        from app.api.helpdesk.tickets import add_my_message

        before = ticket.last_activity_at
        await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="ещё вопрос"),
            real_user,
            real_db_session,
            _redis(),
        )
        await real_db_session.refresh(ticket)
        assert ticket.last_activity_at >= before

    async def test_reply_to_foreign_ticket_404(self, real_db_session, real_user, ticket_of_editor):
        from app.api.helpdesk.tickets import add_my_message

        with pytest.raises(HTTPException) as exc:
            await add_my_message(
                ticket_of_editor.id,
                MessageCreateIn(body_text="попытка"),
                real_user,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 404
