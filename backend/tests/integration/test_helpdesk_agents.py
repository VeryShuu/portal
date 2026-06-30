"""Integration tests for helpdesk agent endpoints + ACL (Этап 3).

Покрывает admin-CRUD агентов, агентские endpoints (list/detail/message/assign/
take/status/reopen) и главное — ACL через ``require_helpdesk_agent``:
не-агент (даже editor) получает 403, агент/admin проходят. Статус-машина
проверяется на интеграционном уровне (assign переводит new→open, take только
для unassigned, status-переходы, reopen из closed).

Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.models.helpdesk import HelpdeskAgent
from app.schemas.helpdesk import MessageCreateIn, TicketAssignIn, TicketStatusIn

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
    """Заявка от reader'а для агентских манипуляций."""
    from app.api.helpdesk.tickets import create_ticket
    from app.schemas.helpdesk import TicketCreateIn

    return await create_ticket(
        TicketCreateIn(subject="Заявка", description="тело"),
        real_user,
        real_db_session,
        _redis(),
    )


# ---------------------------------------------------------------------------
# require_helpdesk_agent (ACL)
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
# Agent list / detail
# ---------------------------------------------------------------------------


class TestAgentListDetail:
    async def test_agent_sees_all_tickets(self, real_db_session, real_editor, real_admin, ticket):
        from app.api.helpdesk.tickets import list_all_tickets

        await _make_agent(real_db_session, real_editor)
        res = await list_all_tickets(
            real_editor, real_db_session, status_filter=None, limit=50, offset=0
        )
        assert res.total >= 1
        assert any(t.id == ticket.id for t in res.items)

    async def test_agent_detail_shows_all_messages_including_future_internal(
        self, real_db_session, real_editor, ticket
    ):
        from app.api.helpdesk.tickets import get_ticket

        await _make_agent(real_db_session, real_editor)
        out = await get_ticket(ticket.id, real_editor, real_db_session)
        # Инвариант первого сообщения — агент видит его.
        assert len(out.messages) == 1
        assert out.messages[0].visibility.value == "public"

    async def test_unassigned_filter(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import list_all_tickets

        await _make_agent(real_db_session, real_editor)
        res = await list_all_tickets(
            real_editor, real_db_session, unassigned=True, limit=50, offset=0
        )
        # Свежий тикет без assignee должен попасть в unassigned.
        assert any(t.id == ticket.id for t in res.items)

    async def test_query_filter_by_subject(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import list_all_tickets

        await _make_agent(real_db_session, real_editor)
        res = await list_all_tickets(real_editor, real_db_session, q="Заявк", limit=50, offset=0)
        assert any(t.id == ticket.id for t in res.items)
        empty = await list_all_tickets(
            real_editor, real_db_session, q="несуществующийзапрос123", limit=50, offset=0
        )
        assert empty.total == 0


# ---------------------------------------------------------------------------
# assign / take
# ---------------------------------------------------------------------------


class TestAssignTake:
    async def test_assign_moves_new_to_open(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import assign_ticket

        await _make_agent(real_db_session, real_editor)
        out = await assign_ticket(
            ticket.id,
            TicketAssignIn(assignee_user_id=real_editor.id),
            real_editor,
            real_db_session,
            _redis(),
        )
        assert out.status.value == "open"
        assert out.assignee_user_id == real_editor.id
        assert out.assigned_at is not None

    async def test_take_only_for_unassigned(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import take_ticket

        await _make_agent(real_db_session, real_editor)
        # Первый take — успех.
        await take_ticket(ticket.id, real_editor, real_db_session, _redis())
        # Второй take (уже назначен) — 409.
        with pytest.raises(HTTPException) as exc:
            await take_ticket(ticket.id, real_editor, real_db_session, _redis())
        assert exc.value.status_code == 409

    async def test_take_assigns_self_and_moves_new_to_open(
        self, real_db_session, real_editor, ticket
    ):
        from app.api.helpdesk.tickets import take_ticket

        await _make_agent(real_db_session, real_editor)
        out = await take_ticket(ticket.id, real_editor, real_db_session, _redis())
        assert out.assignee_user_id == real_editor.id
        assert out.status.value == "open"


# ---------------------------------------------------------------------------
# status / reopen
# ---------------------------------------------------------------------------


class TestStatusReopen:
    async def test_resolve_sets_resolved(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import assign_ticket, change_ticket_status

        await _make_agent(real_db_session, real_editor)
        await assign_ticket(
            ticket.id,
            TicketAssignIn(assignee_user_id=real_editor.id),
            real_editor,
            real_db_session,
            _redis(),
        )
        out = await change_ticket_status(
            ticket.id,
            TicketStatusIn(status="resolved"),
            real_editor,
            real_db_session,
            _redis(),
        )
        assert out.status.value == "resolved"

    async def test_close_sets_closed_fields(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import change_ticket_status

        await _make_agent(real_db_session, real_editor)
        out = await change_ticket_status(
            ticket.id,
            TicketStatusIn(status="closed"),
            real_editor,
            real_db_session,
            _redis(),
        )
        assert out.status.value == "closed"
        assert out.closed_at is not None
        assert out.closed_by_user_id == real_editor.id

    async def test_reopen_from_closed(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import change_ticket_status, reopen_ticket

        await _make_agent(real_db_session, real_editor)
        await change_ticket_status(
            ticket.id,
            TicketStatusIn(status="closed"),
            real_editor,
            real_db_session,
            _redis(),
        )
        out = await reopen_ticket(ticket.id, real_editor, real_db_session, _redis())
        assert out.status.value == "open"
        assert out.closed_at is None
        assert out.closed_by_user_id is None

    async def test_reopen_from_non_closed_returns_409(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import reopen_ticket

        await _make_agent(real_db_session, real_editor)
        with pytest.raises(HTTPException) as exc:
            await reopen_ticket(ticket.id, real_editor, real_db_session, _redis())
        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Agent reply (outbound)
# ---------------------------------------------------------------------------


class TestAgentReply:
    async def test_public_reply_moves_to_pending(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import add_agent_message

        await _make_agent(real_db_session, real_editor)
        out = await add_agent_message(
            ticket.id,
            MessageCreateIn(body_text="Ответ агенту", visibility="public"),
            real_editor,
            real_db_session,
            _redis(),
        )
        assert out.direction.value == "outbound"
        assert out.visibility.value == "public"

        # Перечитаем тикет — публичный ответ агента переводит в pending.
        from app.api.helpdesk.tickets import get_ticket

        detail = await get_ticket(ticket.id, real_editor, real_db_session)
        assert detail.status.value == "pending"

    async def test_first_public_reply_auto_assigns_agent(
        self, real_db_session, real_editor, ticket
    ):
        from app.api.helpdesk.tickets import add_agent_message, get_ticket

        await _make_agent(real_db_session, real_editor)
        await add_agent_message(
            ticket.id,
            MessageCreateIn(body_text="ответ", visibility="public"),
            real_editor,
            real_db_session,
            _redis(),
        )
        detail = await get_ticket(ticket.id, real_editor, real_db_session)
        # ТЗ §4.2.1: первый публичный ответ без assignee → авто-назначение.
        assert detail.assignee_user_id == real_editor.id

    async def test_internal_note_does_not_change_status(self, real_db_session, real_editor, ticket):
        from app.api.helpdesk.tickets import add_agent_message, get_ticket

        await _make_agent(real_db_session, real_editor)
        await add_agent_message(
            ticket.id,
            MessageCreateIn(body_text="заметка", visibility="internal"),
            real_editor,
            real_db_session,
            _redis(),
        )
        detail = await get_ticket(ticket.id, real_editor, real_db_session)
        # Internal-заметка статус не меняет (ТЗ §4.2.1).
        assert detail.status.value == "new"
        # Но сообщение видно агенту.
        assert any(m.visibility.value == "internal" for m in detail.messages)


# ---------------------------------------------------------------------------
# Admin agents CRUD
# ---------------------------------------------------------------------------


class TestAgentsCrud:
    async def test_add_list_delete_agent(self, real_db_session, real_admin, real_editor):
        from app.api.helpdesk.agents import (
            add_agent,
            delete_agent,
            list_agents,
        )
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

        # delete
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
