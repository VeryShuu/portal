"""Integration tests for helpdesk agent operations + ACL (Этап 3).

Покрывает admin-CRUD агентов (роутерный уровень — не multipart), ACL через
``require_helpdesk_agent`` (deps), и агентские операции над тикетами на уровне
**сервисов** (assign/take/status/reopen/message) — сервисы возвращают ORM, что
позволяет проверять статус-переходы напрямую.

Статус-машина: assign переводит new→open, take только для unassigned,
status-переходы, reopen из closed. Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.models.helpdesk import HelpdeskAgent
from app.schemas.helpdesk import MessageCreateIn, TicketCreateIn
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


async def _make_agent(db, user) -> HelpdeskAgent:
    """Добавить пользователя в список агентов поддержки напрямую в БД."""
    agent = HelpdeskAgent(user_id=user.id, notify_new=True)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    """Заявка от reader'а для агентских манипуляций (ORM через сервис)."""
    return await tickets_service.create_ticket(
        real_db_session,
        user=real_user,
        payload=TicketCreateIn(subject="Заявка", description="тело"),
        files=[],
    )


# ---------------------------------------------------------------------------
# require_helpdesk_agent (ACL — deps, не multipart)
# ---------------------------------------------------------------------------


class TestAgentGate:
    async def test_non_agent_non_admin_gets_403(self, real_db_session, real_editor, ticket):
        """Editor без членства в helpdesk_agents — не агент."""
        from app.api.deps import require_helpdesk_agent

        with pytest.raises(HTTPException) as exc:
            await require_helpdesk_agent(real_editor, real_db_session)
        assert exc.value.status_code == 403

    async def test_agent_passes(self, real_db_session, real_editor):
        from app.api.deps import require_helpdesk_agent

        await _make_agent(real_db_session, real_editor)
        assert await require_helpdesk_agent(real_editor, real_db_session) is real_editor

    async def test_admin_always_passes_without_membership(self, real_db_session, real_admin):
        from app.api.deps import require_helpdesk_agent

        # Админ не должен быть в helpdesk_agents — он суперсет агента.
        assert await require_helpdesk_agent(real_admin, real_db_session) is real_admin


# ---------------------------------------------------------------------------
# Agent list / detail (сервисы)
# ---------------------------------------------------------------------------


class TestAgentListDetail:
    async def test_agent_sees_all_tickets(self, real_db_session, real_editor, real_admin, ticket):
        await _make_agent(real_db_session, real_editor)
        total = await tickets_service.count_agent_tickets(real_db_session, status_filter=None)
        items = await tickets_service.list_agent_tickets(
            real_db_session, status_filter=None, limit=50, offset=0
        )
        assert total >= 1
        assert any(t.id == ticket.id for t in items)

    async def test_agent_detail_shows_first_message(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        full = await tickets_service.fetch_ticket_for_agent(real_db_session, ticket_id=ticket.id)
        assert full is not None
        # Инвариант первого сообщения — агент видит его.
        assert len(full.messages) == 1
        assert full.messages[0].visibility == "public"

    async def test_unassigned_filter(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        items = await tickets_service.list_agent_tickets(
            real_db_session, unassigned=True, limit=50, offset=0
        )
        # Свежий тикет без assignee должен попасть в unassigned.
        assert any(t.id == ticket.id for t in items)

    async def test_query_filter_by_subject(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        items = await tickets_service.list_agent_tickets(
            real_db_session, query="Заявк", limit=50, offset=0
        )
        assert any(t.id == ticket.id for t in items)
        total = await tickets_service.count_agent_tickets(
            real_db_session, query="несуществующийзапрос123"
        )
        assert total == 0


# ---------------------------------------------------------------------------
# assign / take (сервисы)
# ---------------------------------------------------------------------------


class TestAssignTake:
    async def test_assign_moves_new_to_open(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        out = await tickets_service.assign_ticket(
            real_db_session, ticket=ticket, assignee_id=real_editor.id
        )
        assert out.status == "open"
        assert out.assignee_user_id == real_editor.id
        assert out.assigned_at is not None

    async def test_take_assigns_self_and_moves_new_to_open(
        self, real_db_session, real_editor, ticket
    ):
        await _make_agent(real_db_session, real_editor)
        out = await tickets_service.assign_ticket(
            real_db_session, ticket=ticket, assignee_id=real_editor.id
        )
        assert out.assignee_user_id == real_editor.id
        assert out.status == "open"


# ---------------------------------------------------------------------------
# status / reopen (сервисы)
# ---------------------------------------------------------------------------


class TestStatusReopen:
    async def test_resolve_sets_resolved(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        await tickets_service.assign_ticket(
            real_db_session, ticket=ticket, assignee_id=real_editor.id
        )
        out = await tickets_service.change_status(
            real_db_session, ticket=ticket, target="resolved", actor=real_editor
        )
        assert out.status == "resolved"

    async def test_close_sets_closed_fields(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        out = await tickets_service.change_status(
            real_db_session, ticket=ticket, target="closed", actor=real_editor
        )
        assert out.status == "closed"
        assert out.closed_at is not None
        assert out.closed_by_user_id == real_editor.id

    async def test_reopen_from_closed(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        await tickets_service.change_status(
            real_db_session, ticket=ticket, target="closed", actor=real_editor
        )
        out = await tickets_service.reopen_ticket(real_db_session, ticket=ticket)
        assert out.status == "open"
        assert out.closed_at is None
        assert out.closed_by_user_id is None

    async def test_reopen_from_non_closed_raises(self, real_db_session, real_editor, ticket):
        from app.services.helpdesk.lifecycle import IllegalTransitionError

        await _make_agent(real_db_session, real_editor)
        with pytest.raises(IllegalTransitionError):
            await tickets_service.reopen_ticket(real_db_session, ticket=ticket)


# ---------------------------------------------------------------------------
# Agent reply (outbound — сервис)
# ---------------------------------------------------------------------------


class TestAgentReply:
    async def test_public_reply_moves_to_pending(self, real_db_session, real_editor, ticket):
        await _make_agent(real_db_session, real_editor)
        msg = await messages_service.add_agent_reply(
            real_db_session,
            ticket=ticket,
            agent=real_editor,
            payload=MessageCreateIn(body_text="Ответ агенту", visibility="public"),
            files=[],
        )
        assert msg.direction == "outbound"
        assert msg.visibility == "public"
        # Публичный ответ агента переводит тикет в pending.
        assert ticket.status == "pending"

    async def test_first_public_reply_auto_assigns_agent(
        self, real_db_session, real_editor, ticket
    ):
        await _make_agent(real_db_session, real_editor)
        await messages_service.add_agent_reply(
            real_db_session,
            ticket=ticket,
            agent=real_editor,
            payload=MessageCreateIn(body_text="ответ", visibility="public"),
            files=[],
        )
        # ТЗ §4.2.1: первый публичный ответ без assignee → авто-назначение.
        assert ticket.assignee_user_id == real_editor.id

    async def test_internal_note_does_not_change_status(self, real_db_session, real_editor, ticket):
        from sqlalchemy import select

        from app.models.helpdesk import HelpdeskMessage

        await _make_agent(real_db_session, real_editor)
        await messages_service.add_agent_reply(
            real_db_session,
            ticket=ticket,
            agent=real_editor,
            payload=MessageCreateIn(body_text="заметка", visibility="internal"),
            files=[],
        )
        # Internal-заметка статус не меняет (ТЗ §4.2.1).
        assert ticket.status == "new"
        # Сообщение создано как internal — прямым запросом мимо session-cache.
        res = await real_db_session.execute(
            select(HelpdeskMessage).where(HelpdeskMessage.ticket_id == ticket.id)
        )
        msgs = res.scalars().all()
        assert any(m.visibility == "internal" for m in msgs)


# ---------------------------------------------------------------------------
# Admin agents CRUD (роутерный уровень — не multipart, возвращает schema)
# ---------------------------------------------------------------------------


class TestAgentsCrud:
    async def test_add_list_delete_agent(self, real_db_session, real_admin, real_editor):
        from app.api.helpdesk.agents import add_agent, delete_agent, list_agents
        from app.schemas.helpdesk import AgentIn

        # add
        created = await add_agent(
            AgentIn(user_id=real_editor.id, notify_new=True),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert created.user_id == real_editor.id
        assert created.user_email == real_editor.email

        # duplicate → 409
        with pytest.raises(HTTPException) as exc:
            await add_agent(AgentIn(user_id=real_editor.id), real_admin, real_db_session, _redis())
        assert exc.value.status_code == 409

        # list
        listed = await list_agents(real_admin, real_db_session)
        assert any(a.user_id == real_editor.id for a in listed.items)

        # delete. После rollback() в duplicate-add выше, атрибуты real_admin
        # expired (специфика SAVEPOINT-сессии тестов; в проде admin приходит
        # свежим из get_current_user). Refresh перед использованием.
        await real_db_session.refresh(real_admin)
        await delete_agent(real_editor.id, real_admin, real_db_session, _redis())

        listed = await list_agents(real_admin, real_db_session)
        assert all(a.user_id != real_editor.id for a in listed.items)

    async def test_add_nonexistent_user_404(self, real_db_session, real_admin):
        from app.api.helpdesk.agents import add_agent
        from app.schemas.helpdesk import AgentIn

        with pytest.raises(HTTPException) as exc:
            await add_agent(AgentIn(user_id=uuid.uuid4()), real_admin, real_db_session, _redis())
        assert exc.value.status_code == 404

    async def test_update_notify_new(self, real_db_session, real_admin, real_editor):
        from app.api.helpdesk.agents import add_agent, update_agent
        from app.schemas.helpdesk import AgentIn

        await add_agent(
            AgentIn(user_id=real_editor.id, notify_new=True),
            real_admin,
            real_db_session,
            _redis(),
        )
        updated = await update_agent(
            real_editor.id,
            AgentIn(user_id=real_editor.id, notify_new=False),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert updated.notify_new is False
