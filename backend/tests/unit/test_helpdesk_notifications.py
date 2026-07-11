"""Unit-тесты in-app уведомлений helpdesk (``services/helpdesk/notifications.py``).

Покрывает получателей и тип/содержимое уведомлений для всех 5 ``notify_*``:
- ``notify_ticket_created`` → все агенты с ``notify_new=True``
- ``notify_ticket_assigned`` → requester (≠actor) + assignee (≠actor)
- ``notify_agent_reply`` → requester
- ``notify_requester_reply`` → assignee (или все агенты, если не назначен)
- ``notify_status_changed`` → requester (closed → тело про reopen-окно)

``_fan_out`` мокается (он делает ``create_notification`` + commit + SSE publish),
чтобы тестировать только логику выбора получателей и формирования title/body.
``_select_agents_to_notify`` покрывается напрямую с mock-сессией.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk import notifications as notif


def _ticket(
    *,
    number: int = 42,
    requester_user_id: uuid.UUID | None = None,
    assignee_user_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    """Билет как SimpleNamespace с ``ticket_number`` property-эмуляцией."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        ticket_number=f"TKT-{number}",
        subject="Тема заявки",
        requester_user_id=requester_user_id,
        assignee_user_id=assignee_user_id,
    )


def _user(*, uid: uuid.UUID | None = None, full_name: str = "Агент") -> SimpleNamespace:
    return SimpleNamespace(id=uid or uuid.uuid4(), full_name=full_name)


def _fake_redis() -> MagicMock:
    return MagicMock()


# ── _select_agents_to_notify ────────────────────────────────────────────────


def _db_returning_agent_ids(agent_ids: list[uuid.UUID]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=agent_ids)))
    db.execute = AsyncMock(return_value=result)
    return db


class TestSelectAgentsToNotify:
    @pytest.mark.asyncio
    async def test_returns_all_agents(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1, a2])
        out = await notif._select_agents_to_notify(db)
        assert out == [a1, a2]

    @pytest.mark.asyncio
    async def test_excludes_user(self):
        a1, excluded = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1])
        out = await notif._select_agents_to_notify(db, exclude_user_id=excluded)
        assert excluded not in out

    @pytest.mark.asyncio
    async def test_require_notify_new_default_true(self):
        """По умолчанию ``require_notify_new=True`` — фильтр активен."""
        a1 = uuid.uuid4()
        db = _db_returning_agent_ids([a1])
        out = await notif._select_agents_to_notify(db)
        assert out == [a1]
        db.execute.assert_awaited_once()


# ── notify_ticket_created → все агенты с notify_new ─────────────────────────


class TestNotifyTicketCreated:
    @pytest.mark.asyncio
    async def test_fans_out_to_agents(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        db = _db_returning_agent_ids([a1, a2])
        redis = _fake_redis()
        ticket = _ticket(number=10)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan:
            sent = await notif.notify_ticket_created(db, redis, ticket=ticket)

        assert sent == 2
        fan.assert_awaited_once()
        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [a1, a2]
        assert kwargs["type_"] == "helpdesk_ticket_created"
        assert "TKT-10" in kwargs["title"]
        assert kwargs["body"] == ticket.subject
        assert kwargs["link"] == f"/helpdesk/tickets/{ticket.id}"


# ── notify_ticket_assigned → requester(≠actor) + assignee(≠actor) ──────────


class TestNotifyTicketAssigned:
    @pytest.mark.asyncio
    async def test_notifies_requester_and_assignee_excluding_actor(self):
        actor = _user()
        requester = uuid.uuid4()
        assignee = _user(full_name="Мария")
        ticket = _ticket(requester_user_id=requester)
        db, redis = MagicMock(), _fake_redis()

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan:
            sent = await notif.notify_ticket_assigned(
                db, redis, ticket=ticket, assignee=assignee, actor=actor
            )

        assert sent == 2
        kwargs = fan.await_args.kwargs
        assert requester in kwargs["user_ids"]
        assert assignee.id in kwargs["user_ids"]
        assert actor.id not in kwargs["user_ids"]
        assert "Мария" in kwargs["body"]
        assert kwargs["link"] == f"/helpdesk/my/{ticket.id}"

    @pytest.mark.asyncio
    async def test_actor_is_assignee_excludes_self(self):
        """Агент берёт тикет сам → уведомляется только requester (assignee=actor)."""
        requester = uuid.uuid4()
        actor = _user(full_name="Сам взял")
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_ticket_assigned(
                MagicMock(), _fake_redis(), ticket=ticket, assignee=actor, actor=actor
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [requester]

    @pytest.mark.asyncio
    async def test_no_requester_and_actor_is_assignee_empty_targets(self):
        """Нет requester и assignee=actor → пустой список получателей (0 отправлено)."""
        actor = _user()
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)) as fan:
            sent = await notif.notify_ticket_assigned(
                MagicMock(), _fake_redis(), ticket=ticket, assignee=actor, actor=actor
            )

        assert sent == 0
        assert fan.await_args.kwargs["user_ids"] == []


# ── notify_agent_reply → requester ──────────────────────────────────────────


class TestNotifyAgentReply:
    @pytest.mark.asyncio
    async def test_notifies_requester(self):
        requester = uuid.uuid4()
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            sent = await notif.notify_agent_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="ответ агент"
            )

        assert sent == 1
        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [requester]
        assert kwargs["type_"] == "helpdesk_agent_reply"
        assert kwargs["body"] == "ответ агент"

    @pytest.mark.asyncio
    async def test_no_requester_zero_sent(self):
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)) as fan:
            sent = await notif.notify_agent_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="x"
            )

        assert sent == 0
        assert fan.await_args.kwargs["user_ids"] == []


# ── notify_requester_reply → assignee или все агенты ────────────────────────


class TestNotifyRequesterReply:
    @pytest.mark.asyncio
    async def test_assigned_ticket_notifies_assignee_only(self):
        assignee = uuid.uuid4()
        ticket = _ticket(assignee_user_id=assignee)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_requester_reply(
                MagicMock(), _fake_redis(), ticket=ticket, body_preview="дополнение"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [assignee]

    @pytest.mark.asyncio
    async def test_unassigned_ticket_notifies_all_agents(self):
        """Нет assignee → все агенты (require_notify_new=False)."""
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        ticket = _ticket(assignee_user_id=None)
        db = _db_returning_agent_ids([a1, a2])

        with (
            patch.object(notif, "_fan_out", new=AsyncMock(return_value=2)) as fan,
        ):
            await notif.notify_requester_reply(
                db, _fake_redis(), ticket=ticket, body_preview="новое сообщение"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["user_ids"] == [a1, a2]
        assert kwargs["type_"] == "helpdesk_requester_reply"
        assert kwargs["link"] == f"/helpdesk/tickets/{ticket.id}"


# ── notify_status_changed → closed добавляет reopen-окно в body ─────────────


class TestNotifyStatusChanged:
    @pytest.mark.asyncio
    async def test_closed_includes_reopen_window(self):
        requester = uuid.uuid4()
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_status_changed(
                MagicMock(), _fake_redis(), ticket=ticket, new_status="closed"
            )

        kwargs = fan.await_args.kwargs
        assert kwargs["body"] is not None
        assert "7" in kwargs["body"]  # HELPDESK_REOPEN_WINDOW_DAYS=7

    @pytest.mark.asyncio
    async def test_resolved_has_null_body(self):
        """resolved → body=None (нет инфо про reopen-окно)."""
        requester = uuid.uuid4()
        ticket = _ticket(requester_user_id=requester)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=1)) as fan:
            await notif.notify_status_changed(
                MagicMock(), _fake_redis(), ticket=ticket, new_status="resolved"
            )

        assert fan.await_args.kwargs["body"] is None
        assert "resolved" in fan.await_args.kwargs["title"]

    @pytest.mark.asyncio
    async def test_no_requester_zero_sent(self):
        ticket = _ticket(requester_user_id=None)

        with patch.object(notif, "_fan_out", new=AsyncMock(return_value=0)):
            sent = await notif.notify_status_changed(
                MagicMock(), _fake_redis(), ticket=ticket, new_status="closed"
            )

        assert sent == 0


# ── _fan_out → транзакционная дисциплина (commit до SSE publish) ────────────


class TestFanOut:
    @pytest.mark.asyncio
    async def test_commits_before_publish_and_returns_count(self):
        """Контракт: create_notification → commit → publish (SSE после commit)."""
        from app.services.helpdesk import notifications as notif_mod

        u1, u2 = uuid.uuid4(), uuid.uuid4()
        publish1, publish2 = AsyncMock(), AsyncMock()
        db = MagicMock()
        db.commit = AsyncMock()
        redis = _fake_redis()

        with patch.object(
            notif_mod,
            "create_notification",
            new=AsyncMock(side_effect=[publish1, publish2]),
        ):
            sent = await notif_mod._fan_out(
                db,
                redis,
                user_ids=[u1, u2],
                type_="x",
                title="t",
                body="b",
                link=None,
            )

        assert sent == 2
        db.commit.assert_awaited_once()
        # Publish callbacks вызваны после commit.
        publish1.assert_awaited_once()
        publish2.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_user_ids_zero_sent(self):
        db = MagicMock()
        db.commit = AsyncMock()

        sent = await notif._fan_out(
            db, _fake_redis(), user_ids=[], type_="x", title="t", body=None, link=None
        )

        assert sent == 0
        db.commit.assert_awaited_once()  # commit всё равно выполняется
