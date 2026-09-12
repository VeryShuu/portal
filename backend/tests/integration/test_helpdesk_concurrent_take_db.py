"""Integration: конкурентное взятие helpdesk-заявки на реальной PostgreSQL.

Аудит тестирования 2026-08-21 (docs/wip/test-audit-remediation.md, фаза
«модули по прод-риску», helpdesk). Головной инвариант модуля (docs/helpdesk.md
§«Гонка взятия»): ``take`` и первый ответ агента читают тикет с
``FOR UPDATE``; проигравший take получает 409 — двойных назначений и дублей
side-эффектов нет. Существующие integration-тесты проверяют 403/409
последовательно; сама гонка (две одновременные транзакции) не покрывалась.

Запуск: ./scripts/test-integration.sh tests/integration/test_helpdesk_concurrent_take_db.py
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _make_user_committed(engine: AsyncEngine, *, name: str) -> uuid.UUID:
    from app.models.user import User

    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = User(
            email=f"hdtake-{uuid.uuid4().hex[:8]}@portal.local",
            full_name=name,
            role="reader",
            auth_source="local",
            current_status="working",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences={},
            updated_at=datetime.now(UTC),
        )
        s.add(user)
        await s.commit()
        return user.id


async def _make_agent_committed(engine: AsyncEngine, user_id: uuid.UUID) -> None:
    from app.models.helpdesk import HelpdeskAgent

    async with AsyncSession(engine, expire_on_commit=False) as s:
        s.add(HelpdeskAgent(user_id=user_id, notify_new=True))
        await s.commit()


async def _make_ticket_committed(engine: AsyncEngine, requester_id: uuid.UUID) -> uuid.UUID:
    from app.models.user import User
    from app.schemas.helpdesk import TicketCreateIn
    from app.services.helpdesk import tickets as tickets_service

    async with AsyncSession(engine, expire_on_commit=False) as s:
        requester = await s.get(User, requester_id)
        assert requester is not None
        ticket = await tickets_service.create_ticket(
            s,
            user=requester,
            payload=TicketCreateIn(subject="Гонка взятия", description="тело"),
            files=[],
        )
        await s.commit()
        return ticket.id


@pytest_asyncio.fixture
async def take_race_cleanup(real_db_engine: AsyncEngine) -> AsyncGenerator[dict, None]:
    state: dict = {"tickets": [], "agents": [], "users": []}
    yield state
    from sqlalchemy import delete

    from app.models.helpdesk import HelpdeskAgent, HelpdeskMessage, HelpdeskTicket
    from app.models.user import User

    async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
        if state["tickets"]:
            await s.execute(
                delete(HelpdeskMessage).where(HelpdeskMessage.ticket_id.in_(state["tickets"]))
            )
            await s.execute(delete(HelpdeskTicket).where(HelpdeskTicket.id.in_(state["tickets"])))
        if state["agents"]:
            await s.execute(delete(HelpdeskAgent).where(HelpdeskAgent.user_id.in_(state["agents"])))
        if state["users"]:
            await s.execute(delete(User).where(User.id.in_(state["users"])))
        await s.commit()


async def _take_in_own_tx(engine: AsyncEngine, *, ticket_id: uuid.UUID, agent_id: uuid.UUID) -> str:
    """Production take (tickets_service.take_ticket_tx) в собственной транзакции.

    audit-review 2026-08-22, P1: тест зовёт настоящую функцию роутера —
    удаление FOR UPDATE/commit'а из production-пути валит тест. Email/outbox
    внутри не сработают: mailbox в тест-БД не сконфигурирован.
    """
    from fastapi import HTTPException

    from app.models.user import User
    from app.services.helpdesk import tickets as tickets_service

    async with AsyncSession(engine, expire_on_commit=False) as s:
        agent = await s.get(User, agent_id)
        assert agent is not None
        try:
            await tickets_service.take_ticket_tx(s, ticket_id=ticket_id, agent=agent)
        except HTTPException as exc:
            if exc.status_code == 409:
                return "conflict"
            raise
        return "took"


class TestConcurrentTake:
    async def test_two_agents_take_same_ticket_exactly_one_wins(
        self, real_db_engine, take_race_cleanup
    ):
        """Двое агентов одновременно берут неназначенную заявку.

        Строчная блокировка (FOR UPDATE) сериализует take'и: победитель
        назначается, проигравший видит assignee после его commit'а → conflict.
        """
        requester_id = await _make_user_committed(real_db_engine, name="Requester")
        agent_a = await _make_user_committed(real_db_engine, name="Agent A")
        agent_b = await _make_user_committed(real_db_engine, name="Agent B")
        for uid in (agent_a, agent_b):
            await _make_agent_committed(real_db_engine, uid)
        ticket_id = await _make_ticket_committed(real_db_engine, requester_id)

        take_race_cleanup["tickets"].append(ticket_id)
        take_race_cleanup["agents"].extend([agent_a, agent_b])
        take_race_cleanup["users"].extend([requester_id, agent_a, agent_b])

        results = await asyncio.gather(
            _take_in_own_tx(real_db_engine, ticket_id=ticket_id, agent_id=agent_a),
            _take_in_own_tx(real_db_engine, ticket_id=ticket_id, agent_id=agent_b),
        )

        assert sorted(results) == ["conflict", "took"], (
            f"ровно один take должен победить, получилось: {results}"
        )
        winner = agent_a if results[0] == "took" else agent_b
        async with AsyncSession(real_db_engine, expire_on_commit=False) as s:
            from app.models.helpdesk import HelpdeskTicket

            ticket = await s.get(HelpdeskTicket, ticket_id)
            assert ticket is not None
            assert str(ticket.assignee_user_id) == str(winner)
            assert ticket.status == "open", "взятие new-заявки переводит её в open"
