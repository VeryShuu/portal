"""Unit-тест эндпоинта ``GET /helpdesk/tickets/counts`` — связка active + unread.

Эндпоинт тонкий (два сервиса + сборка схемы), поэтому тестируется напрямую:
мокируются ``count_assigned_active_tickets`` / ``count_unread_assigned_tickets``
(на уровне модулей сервисов — их же импортирует роутер), проверяется, что оба
зовутся с id одного агента и ответ собирает ``TicketCountsOut(active, unread)``
— контракт красного бейджа меню.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpdesk import tickets as tickets_api
from app.models.user import User
from app.schemas.helpdesk import TicketCountsOut
from app.services.helpdesk import reads as reads_module
from app.services.helpdesk import tickets as tickets_module

AGENT_ID = uuid.uuid4()


def _agent() -> User:
    return cast(User, SimpleNamespace(id=AGENT_ID))


def _db() -> AsyncSession:
    return cast(AsyncSession, object())


@pytest.mark.asyncio
class TestAgentTicketCountsEndpoint:
    async def test_returns_active_and_unread_for_same_agent(self) -> None:
        agent = _agent()
        db = _db()
        count_active = AsyncMock(return_value=4)
        count_unread = AsyncMock(return_value=2)

        with (
            patch.object(tickets_module, "count_assigned_active_tickets", count_active),
            patch.object(reads_module, "count_unread_assigned_tickets", count_unread),
        ):
            out = await tickets_api.get_agent_ticket_counts(agent=agent, db=db)

        assert out == TicketCountsOut(active=4, unread=2)
        # Оба счётчика — про одного агента (id из HelpdeskAgentDep).
        count_active.assert_awaited_once_with(db, user_id=AGENT_ID)
        count_unread.assert_awaited_once_with(db, user_id=AGENT_ID)

    async def test_zero_unread_keeps_badge_gray(self) -> None:
        """Непрочитанных нет → ``unread=0`` (фронт оставляет цифру серой)."""
        with (
            patch.object(
                tickets_module, "count_assigned_active_tickets", AsyncMock(return_value=1)
            ),
            patch.object(reads_module, "count_unread_assigned_tickets", AsyncMock(return_value=0)),
        ):
            out = await tickets_api.get_agent_ticket_counts(agent=_agent(), db=_db())

        assert out == TicketCountsOut(active=1, unread=0)


@pytest.mark.asyncio
class TestMyTicketCountsEndpoint:
    """``GET /tickets/my/counts`` — заявительское зеркало (бейдж «Поддержка»)."""

    async def test_returns_active_and_unread_for_same_user(self) -> None:
        user = _agent()  # тип тот же User; переиспользуем конструктор-заглушку
        db = _db()
        count_active = AsyncMock(return_value=3)
        count_unread = AsyncMock(return_value=1)

        with (
            patch.object(tickets_module, "count_my_active_tickets", count_active),
            patch.object(reads_module, "count_my_unread_tickets", count_unread),
        ):
            out = await tickets_api.get_my_ticket_counts(user=user, db=db)

        assert out == TicketCountsOut(active=3, unread=1)
        count_active.assert_awaited_once_with(db, user_id=AGENT_ID)
        count_unread.assert_awaited_once_with(db, user_id=AGENT_ID)
