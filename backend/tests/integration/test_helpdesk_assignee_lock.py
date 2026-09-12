"""Integration tests for helpdesk assignee-lock (блокировка заявки за агентом).

Правило «одна заявка — один исполнитель»: если на тикете назначен агент
(``assignee_user_id IS NOT NULL``), работу с ним (комментарий, смена статуса,
reopen) ведёт только он. Остальные агенты должны сначала сменить ответственного
на себя через ``POST /assign``. **Админ подчиняется тому же правилу** — без
admin-bypass. Неназначенный тикет доступен любому агенту.

Покрывает роутерный уровень: вызываем endpoint-функции напрямую (как
``test_helpdesk_delete``/``test_helpdesk_agents``), передавая owner/non-owner/
admin и мок-redis. Авто-skip'ается без ``INTEGRATION_DB=true`` (эндпоинты
читают реальную БД через ``_load_agent_ticket``).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.models.helpdesk import HelpdeskAgent
from app.schemas.helpdesk import TicketCreateIn, TicketStatusIn
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    """Мок Redis для ``push_audit_event`` (rpush → Redis-очередь аудита)."""
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


async def _make_user(db, *, role: str = "reader", name: str = "Agent"):
    """Создать пользователя с заданной ролью для теста."""
    from app.models.user import User

    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@portal.local",
        full_name=name,
        department="IT",
        position="Engineer",
        phone="101",
        role=role,
        auth_source="local",
        current_status="working",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        attributes={},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    """Заявка от ``real_user`` (reader) для агентских манипуляций."""
    return await tickets_service.create_ticket(
        real_db_session,
        user=real_user,
        payload=TicketCreateIn(subject="Заявка", description="тело"),
        files=[],
    )


@pytest_asyncio.fixture
async def owner(real_db_session):
    """Агент-владелец заявки (assigned)."""
    user = await _make_user(real_db_session, name="Owner Agent")
    await _make_agent(real_db_session, user)
    return user


@pytest_asyncio.fixture
async def other_agent(real_db_session):
    """Второй агент — не владелец заявки."""
    user = await _make_user(real_db_session, name="Other Agent")
    await _make_agent(real_db_session, user)
    return user


@pytest_asyncio.fixture
async def assigned_ticket(real_db_session, ticket, owner):
    """Заявка, назначенная на ``owner`` (new → open через assign).

    ``assign_ticket`` не делает commit (outbox-инвариант — единый commit в
    роутере). В тесте коммитим явно + refresh, чтобы атрибут был виден."""
    await tickets_service.assign_ticket(real_db_session, ticket=ticket, assignee_id=owner.id)
    await real_db_session.commit()
    await real_db_session.refresh(ticket)
    assert ticket.assignee_user_id == owner.id
    return ticket


# ---------------------------------------------------------------------------
# Comment (POST /tickets/{id}/messages)
# ---------------------------------------------------------------------------


class TestAssigneeLockMessage:
    async def test_owner_can_reply(self, real_db_session, assigned_ticket, owner):
        from app.api.helpdesk.tickets import add_agent_message

        await real_db_session.refresh(owner)
        msg = await add_agent_message(
            assigned_ticket.id,
            owner,
            real_db_session,
            _redis(),
            body_text="ответ владельца",
            body_html="",
            cc=[],
            files=[],
        )
        assert msg.body_text == "ответ владельца"
        assert msg.direction == "outbound"

    async def test_non_owner_forbidden(self, real_db_session, assigned_ticket, other_agent):
        from app.api.helpdesk.tickets import add_agent_message

        await real_db_session.refresh(other_agent)
        with pytest.raises(HTTPException) as exc:
            await add_agent_message(
                assigned_ticket.id,
                other_agent,
                real_db_session,
                _redis(),
                body_text="чужой ответ",
                body_html="",
            )
        assert exc.value.status_code == 403
        assert "assignee_user_id" in exc.value.detail

    async def test_admin_not_owner_forbidden(self, real_db_session, assigned_ticket, real_admin):
        """Админ подчиняется блокировке — без admin-bypass (решение продукта)."""
        from app.api.helpdesk.tickets import add_agent_message

        await real_db_session.refresh(real_admin)
        with pytest.raises(HTTPException) as exc:
            await add_agent_message(
                assigned_ticket.id,
                real_admin,
                real_db_session,
                _redis(),
                body_text="админ-ответ",
                body_html="",
            )
        assert exc.value.status_code == 403

    async def test_unassigned_any_agent_can_reply(self, real_db_session, ticket, other_agent):
        """Неназначенный тикет — любой агент может ответить (блокировка выключена)."""
        from app.api.helpdesk.tickets import add_agent_message

        assert ticket.assignee_user_id is None
        await real_db_session.refresh(other_agent)
        msg = await add_agent_message(
            ticket.id,
            other_agent,
            real_db_session,
            _redis(),
            body_text="беру в работу",
            body_html="",
            cc=[],
            files=[],
        )
        assert msg.body_text == "беру в работу"
        # Auto-assign при первом ответе: отвечавший становится assignee.
        await real_db_session.refresh(ticket)
        assert ticket.assignee_user_id == other_agent.id


# ---------------------------------------------------------------------------
# Status change (PATCH /tickets/{id}/status)
# ---------------------------------------------------------------------------


class TestAssigneeLockStatus:
    async def test_owner_can_change_status(self, real_db_session, assigned_ticket, owner):
        from app.api.helpdesk.tickets import change_ticket_status

        await real_db_session.refresh(owner)
        result = await change_ticket_status(
            assigned_ticket.id,
            TicketStatusIn(status="pending"),
            owner,
            real_db_session,
            _redis(),
        )
        assert result.status == "pending"

    async def test_non_owner_forbidden(self, real_db_session, assigned_ticket, other_agent):
        from app.api.helpdesk.tickets import change_ticket_status

        await real_db_session.refresh(other_agent)
        with pytest.raises(HTTPException) as exc:
            await change_ticket_status(
                assigned_ticket.id,
                TicketStatusIn(status="pending"),
                other_agent,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 403

    async def test_admin_not_owner_forbidden(self, real_db_session, assigned_ticket, real_admin):
        from app.api.helpdesk.tickets import change_ticket_status

        await real_db_session.refresh(real_admin)
        with pytest.raises(HTTPException) as exc:
            await change_ticket_status(
                assigned_ticket.id,
                TicketStatusIn(status="pending"),
                real_admin,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 403

    async def test_unassigned_any_agent_can_close(self, real_db_session, ticket, other_agent):
        from app.api.helpdesk.tickets import change_ticket_status

        assert ticket.assignee_user_id is None
        await real_db_session.refresh(other_agent)
        result = await change_ticket_status(
            ticket.id,
            TicketStatusIn(status="closed"),
            other_agent,
            real_db_session,
            _redis(),
        )
        assert result.status == "closed"


# ---------------------------------------------------------------------------
# Reopen (POST /tickets/{id}/reopen)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def closed_assigned_ticket(real_db_session, assigned_ticket, owner):
    """Назначенная и закрытая владельцем заявка (для reopen-тестов).

    ``change_status`` не делает commit (outbox-инвариант) — коммитим явно."""
    await real_db_session.refresh(owner)
    await tickets_service.change_status(
        real_db_session, ticket=assigned_ticket, target="closed", actor=owner
    )
    await real_db_session.commit()
    await real_db_session.refresh(assigned_ticket)
    assert assigned_ticket.status == "closed"
    return assigned_ticket


class TestAssigneeLockReopen:
    async def test_owner_can_reopen(self, real_db_session, closed_assigned_ticket, owner):
        from app.api.helpdesk.tickets import reopen_ticket

        await real_db_session.refresh(owner)
        result = await reopen_ticket(closed_assigned_ticket.id, owner, real_db_session, _redis())
        assert result.status == "open"

    async def test_non_owner_forbidden(self, real_db_session, closed_assigned_ticket, other_agent):
        from app.api.helpdesk.tickets import reopen_ticket

        await real_db_session.refresh(other_agent)
        with pytest.raises(HTTPException) as exc:
            await reopen_ticket(closed_assigned_ticket.id, other_agent, real_db_session, _redis())
        assert exc.value.status_code == 403

    async def test_admin_not_owner_forbidden(
        self, real_db_session, closed_assigned_ticket, real_admin
    ):
        from app.api.helpdesk.tickets import reopen_ticket

        await real_db_session.refresh(real_admin)
        with pytest.raises(HTTPException) as exc:
            await reopen_ticket(closed_assigned_ticket.id, real_admin, real_db_session, _redis())
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Reassign stays open to all agents (POST /tickets/{id}/assign, /take)
# ---------------------------------------------------------------------------


class TestAssigneeLockReassign:
    """Смена ответственного доступна всем агентам всегда — это канал
    «передать заявку / назначить себя». Блокировка НЕ распространяется."""

    async def test_other_agent_can_reassign_to_self(
        self, real_db_session, assigned_ticket, owner, other_agent
    ):
        from app.api.helpdesk.tickets import assign_ticket
        from app.schemas.helpdesk import TicketAssignIn

        # Заявка назначена на owner, но other_agent может переназначить на себя.
        assert assigned_ticket.assignee_user_id == owner.id
        await real_db_session.refresh(other_agent)
        result = await assign_ticket(
            assigned_ticket.id,
            TicketAssignIn(assignee_user_id=other_agent.id),
            other_agent,
            real_db_session,
            _redis(),
        )
        assert result.assignee_user_id == other_agent.id
        # Теперь other_agent — владелец и может отвечать.
        await real_db_session.refresh(assigned_ticket)
        assert assigned_ticket.assignee_user_id == other_agent.id

    async def test_assign_not_found_for_non_agent(
        self, real_db_session, assigned_ticket, other_agent
    ):
        from app.api.helpdesk.tickets import assign_ticket
        from app.schemas.helpdesk import TicketAssignIn

        # Передача не-агенту → 404 (валидация таргета в роутере).
        await real_db_session.refresh(other_agent)
        with pytest.raises(HTTPException) as exc:
            await assign_ticket(
                assigned_ticket.id,
                TicketAssignIn(assignee_user_id=uuid.uuid4()),
                other_agent,
                real_db_session,
                _redis(),
            )
        assert exc.value.status_code == 404

    async def test_take_unassigned_works(self, real_db_session, ticket, other_agent):
        from app.api.helpdesk.tickets import take_ticket

        assert ticket.assignee_user_id is None
        await real_db_session.refresh(other_agent)
        result = await take_ticket(ticket.id, other_agent, real_db_session, _redis())
        assert result.assignee_user_id == other_agent.id
        # DB-проверка.
        from app.models.helpdesk import HelpdeskTicket

        res = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == ticket.id)
        )
        db_ticket = res.scalar_one()
        assert db_ticket.assignee_user_id == other_agent.id
