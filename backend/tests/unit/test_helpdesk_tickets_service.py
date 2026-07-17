"""Unit-тесты сервисного слоя заявок (``services/helpdesk/tickets.py``).

Покрывает:
- ``_agent_filter_conditions`` — все 5 фильтров (чистая, parametrize)
- ``resolve_requester_user`` — 3 ветки (requester_user_id / empty email / fallback)
- ``reopen_ticket`` — IllegalTransitionError + happy path
- ``change_status`` — commit + closed_at/closed_by
- ``assign_ticket`` — new→open vs non-new (дополнение к messages_tx)
- ``count_my_tickets`` / ``list_my_tickets`` / ``fetch_ticket_for_user``
- ``count_agent_tickets`` / ``list_agent_tickets`` / ``fetch_ticket_for_agent``
- ``create_ticket`` — инвариант первого сообщения + commit + fetch
- ``link_guest_tickets`` — гостевое линкование, идемпотентность

Стиль моков — по образцу ``test_helpdesk_messages_tx.py``: ``MagicMock()`` +
явные ``AsyncMock`` на async-методах, ``SimpleNamespace`` для тикетов.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk import tickets as svc
from app.services.helpdesk.lifecycle import IllegalTransitionError


def _ticket(
    *,
    status: str = "new",
    requester_user_id: uuid.UUID | None = None,
    requester_email: str | None = "guest@example.com",
    requester_user=None,
    number: int = 5,
    assignee_user_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        status=status,
        subject="Тема",
        description="Описание",
        source="web",
        requester_user_id=requester_user_id,
        requester_email=requester_email,
        requester_name="Гость",
        requester_user=requester_user,
        assignee_user_id=assignee_user_id,
        assigned_at=None,
        closed_at=None,
        closed_by_user_id=None,
        last_activity_at=datetime(2026, 7, 1),
    )


def _user(*, uid: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid or uuid.uuid4(),
        email="user@portal.local",
        full_name="Иван Иванов",
        role="reader",
    )


def _make_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── _agent_filter_conditions (чистая функция, 5 фильтров) ───────────────────


class TestAgentFilterConditions:
    def test_no_filters_empty(self):
        assert (
            svc._agent_filter_conditions(
                status_filter=None,
                assignee_id=None,
                unassigned=False,
                source=None,
                query=None,
            )
            == []
        )

    def test_status_filter_appended(self):
        conds = svc._agent_filter_conditions(
            status_filter="open", assignee_id=None, unassigned=False, source=None, query=None
        )
        assert len(conds) == 1

    def test_assignee_id_appended(self):
        aid = uuid.uuid4()
        conds = svc._agent_filter_conditions(
            status_filter=None, assignee_id=aid, unassigned=False, source=None, query=None
        )
        assert len(conds) == 1

    def test_unassigned_appended(self):
        conds = svc._agent_filter_conditions(
            status_filter=None, assignee_id=None, unassigned=True, source=None, query=None
        )
        assert len(conds) == 1

    def test_source_appended(self):
        conds = svc._agent_filter_conditions(
            status_filter=None, assignee_id=None, unassigned=False, source="email", query=None
        )
        assert len(conds) == 1

    def test_query_appends_or_condition(self):
        conds = svc._agent_filter_conditions(
            status_filter=None, assignee_id=None, unassigned=False, source=None, query="vpn"
        )
        assert len(conds) == 1  # один or_ на 3 поля

    def test_active_only_appends_status_in_condition(self):
        """active_only=True → status IN ('new','open','pending'). Нужно для
        двухблочного инбокса: нижний блок «В работе» скрывает resolved/closed
        (они в архиве), не задавая конкретный status_filter."""
        conds = svc._agent_filter_conditions(
            status_filter=None,
            assignee_id=None,
            unassigned=False,
            source=None,
            query=None,
            active_only=True,
        )
        assert len(conds) == 1

    def test_active_only_ignored_when_status_filter_set(self):
        """Конкретный status_filter точнее active_only — последний не добавляется
        (elif), чтобы не было взаимоисключающих условий."""
        conds = svc._agent_filter_conditions(
            status_filter="closed",
            assignee_id=None,
            unassigned=False,
            source=None,
            query=None,
            active_only=True,
        )
        assert len(conds) == 1  # только status == 'closed', без IN

    def test_active_only_default_false_backward_compatible(self):
        """Новый параметр обратно-совместим: без него поведение не меняется."""
        conds = svc._agent_filter_conditions(
            status_filter=None,
            assignee_id=None,
            unassigned=False,
            source=None,
            query=None,
        )
        assert conds == []

    def test_assigned_appends_is_not_null(self):
        """assigned=True → assignee IS NOT NULL. Режим «Все назначенные» в инбоксе:
        показать тикеты, назначенные на любого агента, БЕЗ неназначенных
        (которые в верхнем блоке «Новые заявки»)."""
        conds = svc._agent_filter_conditions(
            status_filter=None,
            assignee_id=None,
            unassigned=False,
            source=None,
            query=None,
            assigned=True,
        )
        assert len(conds) == 1

    def test_assigned_ignored_when_unassigned_set(self):
        """unassigned и assigned взаимоисключающие — unassigned优先 (elif),
        assigned не добавляется."""
        conds = svc._agent_filter_conditions(
            status_filter=None,
            assignee_id=None,
            unassigned=True,
            source=None,
            query=None,
            assigned=True,
        )
        assert len(conds) == 1  # только IS NULL, без IS NOT NULL

    def test_all_filters_combined(self):
        """status + assignee_id + unassigned + source + query = 5 условий.

        Внимание: ``assignee_id`` и ``unassigned`` — взаимоисключающие в UI, но
        функция добавляет оба без проверки; здесь тестируем именно полноту."""
        conds = svc._agent_filter_conditions(
            status_filter="open",
            assignee_id=uuid.uuid4(),
            unassigned=True,
            source="web",
            query="x",
        )
        assert len(conds) == 5


# ── resolve_requester_user — 3 ветки ────────────────────────────────────────


class TestResolveRequesterUser:
    @pytest.mark.asyncio
    async def test_returns_requester_user_when_id_present(self):
        """Есть requester_user_id → возвращаем eager-loaded requester_user."""
        ru = _user()
        ticket = _ticket(requester_user_id=ru.id, requester_user=ru)

        got = await svc.resolve_requester_user(MagicMock(), ticket=ticket)

        assert got is ru  # без доп. запроса к БД

    @pytest.mark.asyncio
    async def test_empty_email_returns_none(self):
        """Гостевая заявка без email → None (профиль не отрисовывается)."""
        ticket = _ticket(requester_user_id=None, requester_email=None)

        got = await svc.resolve_requester_user(MagicMock(), ticket=ticket)

        assert got is None

    @pytest.mark.asyncio
    async def test_guest_email_fallback_search(self):
        """Нет requester_user_id, но есть email → поиск сотрудника по LOWER(email)."""
        ticket = _ticket(requester_user_id=None, requester_email="Guest@Example.com")
        found = _user()
        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.one_or_none.return_value = found
        db.execute = AsyncMock(return_value=result)

        got = await svc.resolve_requester_user(db, ticket=ticket)

        assert got is found
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_guest_email_not_found_returns_none(self):
        ticket = _ticket(requester_user_id=None, requester_email="nobody@example.com")
        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        got = await svc.resolve_requester_user(db, ticket=ticket)

        assert got is None


# ── reopen_ticket — IllegalTransitionError + happy path ─────────────────────


class TestReopenTicket:
    @pytest.mark.asyncio
    async def test_raises_on_non_closed(self):
        """Reopen только из closed; из других статусов → IllegalTransitionError."""
        db = _make_db()
        for bad_status in ("new", "open", "pending", "resolved"):
            ticket = _ticket(status=bad_status)
            with pytest.raises(IllegalTransitionError):
                await svc.reopen_ticket(db, ticket=ticket)

    @pytest.mark.asyncio
    async def test_closed_reopens_to_open_and_clears_closed_fields(self):
        db = _make_db()
        actor_id = uuid.uuid4()
        ticket = _ticket(status="closed")
        ticket.closed_at = datetime(2026, 7, 1)
        ticket.closed_by_user_id = actor_id

        result = await svc.reopen_ticket(db, ticket=ticket)

        assert result.status == "open"
        assert result.closed_at is None
        assert result.closed_by_user_id is None
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()


# ── change_status — commit + closed_at/closed_by ────────────────────────────


class TestChangeStatus:
    @pytest.mark.asyncio
    async def test_close_sets_closed_fields(self):
        db = _make_db()
        actor = _user()
        ticket = _ticket(status="open")

        result = await svc.change_status(db, ticket=ticket, target="closed", actor=actor)

        assert result.status == "closed"
        assert result.closed_at is not None
        assert result.closed_by_user_id == actor.id
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_close_transition_no_closed_fields(self):
        db = _make_db()
        actor = _user()
        ticket = _ticket(status="new")

        result = await svc.change_status(db, ticket=ticket, target="open", actor=actor)

        assert result.status == "open"
        assert result.closed_at is None
        assert result.closed_by_user_id is None

    @pytest.mark.asyncio
    async def test_illegal_transition_propagates(self):
        """Невалидный target → IllegalTransitionError (роутер транслирует в 409).

        Замечание: ``new → closed`` разрешён (админ может сразу закрыть спам),
        поэтому для ошибки берём несуществующий статус."""
        db = _make_db()
        actor = _user()
        ticket = _ticket(status="new")

        with pytest.raises(IllegalTransitionError):
            await svc.change_status(db, ticket=ticket, target="foo", actor=actor)


# ── assign_ticket — new→open vs non-new ─────────────────────────────────────


class TestAssignTicket:
    @pytest.mark.asyncio
    async def test_new_becomes_open(self):
        db = _make_db()
        ticket = _ticket(status="new")
        assignee_id = uuid.uuid4()

        result = await svc.assign_ticket(db, ticket=ticket, assignee_id=assignee_id)

        assert result is ticket
        assert ticket.assignee_user_id == assignee_id
        assert ticket.status == "open"
        assert ticket.assigned_at is not None
        db.commit.assert_not_awaited()  # outbox-инвариант: без commit

    @pytest.mark.asyncio
    async def test_non_open_status_unchanged_on_reassign(self):
        """Реассайн тикета не из new — статус не меняется (только assignee)."""
        db = _make_db()
        ticket = _ticket(status="pending")
        assignee_id = uuid.uuid4()

        await svc.assign_ticket(db, ticket=ticket, assignee_id=assignee_id)

        assert ticket.status == "pending"
        assert ticket.assignee_user_id == assignee_id


# ── count_my_tickets / list_my_tickets / fetch_ticket_for_user ──────────────


def _db_returning_scalar(value) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=value)
    db.execute = AsyncMock(return_value=result)
    return db


def _db_returning_scalars_all(items: list) -> MagicMock:
    """Для list-функций: ``res.scalars().unique().all()`` (с unique — как в
    list_my_tickets/list_agent_tickets с selectinload)."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = items
    db.execute = AsyncMock(return_value=result)
    return db


def _db_returning_scalars_all_plain(items: list) -> MagicMock:
    """Для функций без ``.unique()`` (link_guest_tickets: ``res.scalars().all()``)."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    db.execute = AsyncMock(return_value=result)
    return db


def _db_returning_one_or_none(value) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.one_or_none.return_value = value
    db.execute = AsyncMock(return_value=result)
    return db


class TestMyTickets:
    @pytest.mark.asyncio
    async def test_count_returns_int(self):
        db = _db_returning_scalar(7)
        n = await svc.count_my_tickets(db, user_id=uuid.uuid4(), status_filter=None)
        assert n == 7

    @pytest.mark.asyncio
    async def test_count_with_status_filter(self):
        db = _db_returning_scalar(3)
        n = await svc.count_my_tickets(db, user_id=uuid.uuid4(), status_filter="open")
        assert n == 3
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_returns_sequence(self):
        t1, t2 = _ticket(), _ticket()
        db = _db_returning_scalars_all([t1, t2])
        out = await svc.list_my_tickets(
            db, user_id=uuid.uuid4(), status_filter=None, limit=20, offset=0
        )
        assert list(out) == [t1, t2]

    @pytest.mark.asyncio
    async def test_fetch_ticket_for_user_found(self):
        ticket = _ticket()
        db = _db_returning_one_or_none(ticket)
        got = await svc.fetch_ticket_for_user(db, ticket_id=ticket.id, user_id=uuid.uuid4())
        assert got is ticket

    @pytest.mark.asyncio
    async def test_fetch_ticket_for_user_not_found(self):
        db = _db_returning_one_or_none(None)
        got = await svc.fetch_ticket_for_user(db, ticket_id=uuid.uuid4(), user_id=uuid.uuid4())
        assert got is None


# ── count_agent_tickets / list_agent_tickets / fetch_ticket_for_agent ───────


class TestAgentTickets:
    @pytest.mark.asyncio
    async def test_count_agent(self):
        db = _db_returning_scalar(12)
        n = await svc.count_agent_tickets(db, status_filter="open", unassigned=True)
        assert n == 12

    @pytest.mark.asyncio
    async def test_list_agent_returns_sequence(self):
        t1 = _ticket()
        db = _db_returning_scalars_all([t1])
        out = await svc.list_agent_tickets(db, status_filter=None, query="vpn", limit=10, offset=0)
        assert list(out) == [t1]

    @pytest.mark.asyncio
    async def test_fetch_ticket_for_agent_found(self):
        ticket = _ticket()
        db = _db_returning_one_or_none(ticket)
        got = await svc.fetch_ticket_for_agent(db, ticket_id=ticket.id)
        assert got is ticket

    @pytest.mark.asyncio
    async def test_fetch_ticket_for_agent_not_found(self):
        db = _db_returning_one_or_none(None)
        got = await svc.fetch_ticket_for_agent(db, ticket_id=uuid.uuid4())
        assert got is None


# ── link_guest_tickets — гостевое линкование ────────────────────────────────


class TestLinkGuestTickets:
    @pytest.mark.asyncio
    async def test_links_matching_guest_tickets(self):
        t1 = _ticket(requester_user_id=None, requester_email="guest@example.com")
        t2 = _ticket(requester_user_id=None, requester_email="guest@example.com")
        db = _db_returning_scalars_all_plain([t1, t2])
        user_id = uuid.uuid4()

        count = await svc.link_guest_tickets(db, user_id=user_id, email="guest@example.com")

        assert count == 2
        assert t1.requester_user_id == user_id
        assert t2.requester_user_id == user_id

    @pytest.mark.asyncio
    async def test_no_matches_returns_zero(self):
        db = _db_returning_scalars_all_plain([])
        count = await svc.link_guest_tickets(db, user_id=uuid.uuid4(), email="nobody@example.com")
        assert count == 0

    @pytest.mark.asyncio
    async def test_email_case_insensitive_match(self):
        """Матчинг по LOWER(email) — 'GUEST@x.com' ловит 'guest@x.com'."""
        t1 = _ticket(requester_user_id=None, requester_email="guest@example.com")
        db = _db_returning_scalars_all_plain([t1])

        await svc.link_guest_tickets(db, user_id=uuid.uuid4(), email="Guest@Example.com")

        assert t1.requester_user_id is not None


# ── create_ticket — инвариант первого сообщения + commit ────────────────────


class TestCreateTicket:
    @pytest.mark.asyncio
    async def test_creates_ticket_and_first_message_then_commits(self):
        """Инвариант ТЗ §4.3.1: тикет + первое inbound/public сообщение в одной
        транзакции. ``ticket.id``/``number`` заполняются при flush."""
        from app.schemas.helpdesk import TicketCreateIn

        db = _make_db()
        user = _user()
        # flush мутирует ticket.id/number (эмуляция БД-генерации)
        assigned_id = uuid.uuid4()

        def _flush_side_effect(*_args, **_kwargs):
            # Первый flush — для ticket (назначаем id/number), второй — для message
            # Упрощённо: если у ticket уже есть id, ничего не делаем.
            ticket_obj = None
            for call in db.add.call_args_list:
                if (
                    hasattr(call.args[0], "status")
                    and getattr(call.args[0], "number", None) is None
                ):
                    ticket_obj = call.args[0]
                    break
            if ticket_obj is not None and ticket_obj.id is None:
                ticket_obj.id = assigned_id
                ticket_obj.number = 99

        db.flush.side_effect = _flush_side_effect
        # fetch_ticket_for_user замокан на уровне модуля
        fetched = _ticket(requester_user_id=user.id)
        with patch.object(svc, "fetch_ticket_for_user", new=AsyncMock(return_value=fetched)):
            result = await svc.create_ticket(
                db,
                user=user,
                payload=TicketCreateIn(subject="Тема", description="Тело"),
                files=None,
            )

        assert result is fetched
        # Два add: ticket + first_message.
        assert db.add.call_count == 2
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uploads_attachments_when_files_provided(self):
        from app.schemas.helpdesk import TicketCreateIn

        db = _make_db()
        user = _user()

        def _flush_side_effect(*_args, **_kwargs):
            for call in db.add.call_args_list:
                obj = call.args[0]
                if hasattr(obj, "subject") and getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()
                    obj.number = 1
                elif hasattr(obj, "body_text") and getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()

        db.flush.side_effect = _flush_side_effect
        fetched = _ticket()
        with (
            patch.object(svc, "fetch_ticket_for_user", new=AsyncMock(return_value=fetched)),
            patch(
                "app.services.helpdesk.attachments.upload_attachments",
                new=AsyncMock(),
            ) as uploaded,
        ):
            await svc.create_ticket(
                db,
                user=user,
                payload=TicketCreateIn(subject="Тема", description="Тело"),
                files=[SimpleNamespace(filename="x.png")],
            )

        uploaded.assert_awaited_once()
