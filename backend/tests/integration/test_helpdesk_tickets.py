"""Integration tests for the requester web-flow of Helpdesk (Этап 2).

Покрывает создание тикета (с инвариантом первого сообщения), списочное чтение
«своих», карточку с публичными сообщениями, ответ инициатора и ACL «только
свои» на уровне сервисного слоя (``fetch_ticket_for_user`` возвращает ``None``
для чужого тикета → роутер транслирует это в 404).

Тесты вызывают **сервисы** (как ``test_directories_db``), а не роутеры:
роутеры после Этапа 4 принимают ``multipart/form-data`` (Form/File —
зависимости FastAPI, не значения), и возвращают Pydantic-схемы. Бизнес-логика
и БД-инварианты живут в сервисах, что и проверяется здесь. Роутерный слой
(schema-mapping, audit, notify, ACL→404) покрывается unit- и E2E-тестами.

Авто-skip'ается без ``INTEGRATION_DB=true`` (нет реальной PostgreSQL).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.models.helpdesk import HelpdeskTicket
from app.schemas.helpdesk import MessageCreateIn, TicketCreateIn
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


def _payload(subject: str = "Не работает VPN") -> TicketCreateIn:
    return TicketCreateIn(subject=subject, description="Подробности заявки")


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    """Заявка, созданная ``real_user`` (reader) через web-flow."""
    return await tickets_service.create_ticket(
        real_db_session, user=real_user, payload=_payload(), files=[]
    )


@pytest_asyncio.fixture
async def ticket_of_editor(real_db_session, real_editor):
    """Заявка, принадлежащая другому пользователю (editor) — для ACL-проверок."""
    return await tickets_service.create_ticket(
        real_db_session,
        user=real_editor,
        payload=TicketCreateIn(subject="Чужая заявка", description="не моя"),
        files=[],
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
        full = await tickets_service.fetch_ticket_for_user(
            real_db_session, ticket_id=ticket.id, user_id=ticket.requester_user_id
        )
        assert full is not None
        public = [m for m in full.messages if m.visibility != "internal"]
        assert len(public) == 1
        first = public[0]
        assert first.direction == "inbound"
        assert first.visibility == "public"
        assert first.source == "web"
        assert first.body_text == ticket.description
        assert first.author_user_id == ticket.requester_user_id


# ---------------------------------------------------------------------------
# Список своих + ACL «только свои»
# ---------------------------------------------------------------------------


class TestListMyTickets:
    async def test_only_own_tickets_visible(
        self, real_db_session, real_user, ticket, ticket_of_editor
    ):
        total = await tickets_service.count_my_tickets(
            real_db_session, user_id=real_user.id, status_filter=None
        )
        items = await tickets_service.list_my_tickets(
            real_db_session, user_id=real_user.id, status_filter=None, limit=50, offset=0
        )
        ids = {t.id for t in items}
        assert total == 1
        assert ticket.id in ids
        # Чужая заявка editor'а не видна reader'у.
        assert ticket_of_editor.id not in ids

    async def test_status_filter(self, real_db_session, real_user, ticket):
        assert (
            await tickets_service.count_my_tickets(
                real_db_session, user_id=real_user.id, status_filter="new"
            )
            == 1
        )
        assert (
            await tickets_service.count_my_tickets(
                real_db_session, user_id=real_user.id, status_filter="closed"
            )
            == 0
        )

    async def test_pagination(self, real_db_session, real_user, ticket):
        items = await tickets_service.list_my_tickets(
            real_db_session, user_id=real_user.id, status_filter=None, limit=10, offset=0
        )
        assert len(items) == 1
        assert items[0].id == ticket.id


# ---------------------------------------------------------------------------
# Карточка + ACL (сервисный уровень: None = «не твой»)
# ---------------------------------------------------------------------------


class TestFetchTicketForUser:
    async def test_own_ticket_returned(self, real_db_session, real_user, ticket):
        full = await tickets_service.fetch_ticket_for_user(
            real_db_session, ticket_id=ticket.id, user_id=real_user.id
        )
        assert full is not None
        assert full.id == ticket.id
        # Публичный таймлайн содержит первое сообщение.
        assert len(full.messages) == 1
        assert full.messages[0].visibility == "public"

    async def test_foreign_ticket_returns_none(self, real_db_session, real_user, ticket_of_editor):
        """ACL на уровне сервиса: чужой тикет → None (роутер сделает 404)."""
        full = await tickets_service.fetch_ticket_for_user(
            real_db_session, ticket_id=ticket_of_editor.id, user_id=real_user.id
        )
        assert full is None

    async def test_random_uuid_returns_none(self, real_db_session, real_user):
        full = await tickets_service.fetch_ticket_for_user(
            real_db_session, ticket_id=uuid.uuid4(), user_id=real_user.id
        )
        assert full is None


# ---------------------------------------------------------------------------
# Ответ инициатора + статус-переходы
# ---------------------------------------------------------------------------


class TestAddRequesterReply:
    async def _set_status(self, db, ticket, status_value: str) -> None:
        """Прямое переключение статуса для проверки переходов (агентских
        endpoints на этапе 2 ещё нет — меняем в БД напрямую)."""
        ticket.status = status_value
        await db.flush()

    async def test_reply_appended_as_inbound_public(self, real_db_session, real_user, ticket):
        msg = await messages_service.add_requester_reply(
            real_db_session,
            ticket=ticket,
            user=real_user,
            payload=MessageCreateIn(body_text="Дополнение от клиента"),
            files=[],
        )
        assert msg.direction == "inbound"
        assert msg.visibility == "public"
        assert msg.body_text == "Дополнение от клиента"

    async def test_reply_reopens_pending(self, real_db_session, real_user, ticket):
        await self._set_status(real_db_session, ticket, "pending")
        await messages_service.add_requester_reply(
            real_db_session,
            ticket=ticket,
            user=real_user,
            payload=MessageCreateIn(body_text="ответ"),
            files=[],
        )
        assert ticket.status == "open"

    async def test_reply_reopens_resolved_without_window(self, real_db_session, real_user, ticket):
        """ТЗ §4.2: resolved → open по любому ответу клиента, без окна."""
        await self._set_status(real_db_session, ticket, "resolved")
        await messages_service.add_requester_reply(
            real_db_session,
            ticket=ticket,
            user=real_user,
            payload=MessageCreateIn(body_text="не подтверждено"),
            files=[],
        )
        assert ticket.status == "open"

    async def test_reply_updates_last_activity(self, real_db_session, real_user, ticket):
        before = ticket.last_activity_at
        await messages_service.add_requester_reply(
            real_db_session,
            ticket=ticket,
            user=real_user,
            payload=MessageCreateIn(body_text="ещё вопрос"),
            files=[],
        )
        assert ticket.last_activity_at >= before


# ---------------------------------------------------------------------------
# Профиль заявителя: resolve_requester_user (гостевой fallback по email)
# ---------------------------------------------------------------------------


class TestResolveRequesterUser:
    """Поиск пользователя-заявителя для построения профиля в карточке тикета.

    * web-тикет с requester_user_id → eager-loaded requester_user.
    * гостевой тикет (requester_user_id IS NULL), email совпадает с сотрудником
      → находится через fallback по LOWER(email).
    * гостевой тикет с email, которого нет в базе → None.
    """

    async def test_owned_ticket_returns_requester(self, real_db_session, ticket, real_user):
        # ticket создан через web-flow, requester_user_id = real_user.id.
        full = await tickets_service.fetch_ticket_for_agent(
            real_db_session, ticket_id=ticket.id
        )
        assert full is not None
        requester = await tickets_service.resolve_requester_user(
            real_db_session, ticket=full
        )
        assert requester is not None
        assert requester.id == real_user.id

    async def test_guest_ticket_matched_by_email(self, real_db_session, real_user):
        """Гостевая заявка без requester_user_id, но email = существующему юзеру."""
        guest = HelpdeskTicket(
            subject="Гостевая",
            description="тело",
            status="new",
            source="email",
            requester_user_id=None,
            requester_email=real_user.email.upper(),  # case-insensitive
            requester_name="Гость",
        )
        real_db_session.add(guest)
        await real_db_session.flush()
        requester = await tickets_service.resolve_requester_user(
            real_db_session, ticket=guest
        )
        assert requester is not None
        assert requester.id == real_user.id

    async def test_guest_ticket_unknown_email_returns_none(self, real_db_session):
        guest = HelpdeskTicket(
            subject="Гостевая",
            description="тело",
            status="new",
            source="email",
            requester_user_id=None,
            requester_email="nobody@nowhere.local",
            requester_name="Гость",
        )
        real_db_session.add(guest)
        await real_db_session.flush()
        requester = await tickets_service.resolve_requester_user(
            real_db_session, ticket=guest
        )
        assert requester is None

