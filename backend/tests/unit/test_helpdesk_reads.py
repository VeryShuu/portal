"""Unit-тесты ``services/helpdesk/reads.py`` — agent read-state (миграция 080).

Покрытие (БД мокируется, проверяется control-flow + возвращаемые значения):

* ``mark_ticket_seen`` — UPSERT (один execute, без commit; caller контролирует
  транзакцию — outbox-инвариант AGENTS.md). Возвращает переданный ``now``.
* ``has_unread_requester_messages`` — EXISTS-запрос возвращает bool.
* ``enrich_with_unread`` — один execute для всего списка; пустой вход → no-op
  (ранний выход без запроса); возвращает map для всех входных ``ticket_id``.

Контракт «непрочитанности» (только публичные входящие сообщения от заявителя)
тестируется на integration-уровне (см. ``test_helpdesk_tickets.py``), т.к.
требует реальных данных; здесь — структурные проверки SQL-control-flow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.helpdesk import reads as reads_svc

TICKET_ID = uuid.uuid4()
TICKET_ID_2 = uuid.uuid4()
USER_ID = uuid.uuid4()


def _result(*, scalar=None, rows=None) -> MagicMock:
    """Мок ``Result``: ``scalar_one()`` для EXISTS/bool, ``all()`` для enrich."""
    r = MagicMock()
    r.scalar_one = MagicMock(return_value=scalar)
    rows_iter = rows or []
    r.all = MagicMock(return_value=rows_iter)
    return r


def _make_db(execute_results: list) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.commit = AsyncMock()
    return db


def _ticket(*, id_: uuid.UUID | None = None) -> SimpleNamespace:
    """Минимальная заглушка ``HelpdeskTicket`` — нужен только ``id``."""
    return SimpleNamespace(id=id_ or uuid.uuid4())


@pytest.mark.asyncio
class TestMarkTicketSeen:
    async def test_calls_execute_once_no_commit(self) -> None:
        """UPSERT = один ``db.execute`` (pg_insert.on_conflict_do_update).
        ``db.commit`` НЕ вызывается — caller контролирует транзакцию."""
        db = _make_db([_result()])
        seen_at = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)

        result = await reads_svc.mark_ticket_seen(
            db, ticket_id=TICKET_ID, user_id=USER_ID, now=seen_at
        )

        assert result == seen_at
        db.execute.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_defaults_to_now_utc(self) -> None:
        """Без явного ``now`` берётся ``datetime.now(UTC)``."""
        db = _make_db([_result()])
        before = datetime.now(UTC)

        result = await reads_svc.mark_ticket_seen(db, ticket_id=TICKET_ID, user_id=USER_ID)

        after = datetime.now(UTC)
        assert before <= result <= after
        assert result.tzinfo == UTC


@pytest.mark.asyncio
class TestHasUnreadRequesterMessages:
    async def test_returns_bool_from_scalar(self) -> None:
        """``True`` когда EXISTS вернул ``True`` (есть inbound-public новее last_seen)."""
        db = _make_db([_result(scalar=True)])
        result = await reads_svc.has_unread_requester_messages(
            db, ticket_id=TICKET_ID, user_id=USER_ID
        )
        assert result is True

    async def test_returns_false_when_no_unread(self) -> None:
        """``False`` когда все inbound-public уже прочитаны (или их нет)."""
        db = _make_db([_result(scalar=False)])
        result = await reads_svc.has_unread_requester_messages(
            db, ticket_id=TICKET_ID, user_id=USER_ID
        )
        assert result is False

    async def test_executes_one_query(self) -> None:
        """Один запрос на проверку (EXISTS — самый дешёвый путь)."""
        db = _make_db([_result(scalar=True)])
        await reads_svc.has_unread_requester_messages(db, ticket_id=TICKET_ID, user_id=USER_ID)
        assert db.execute.await_count == 1


@pytest.mark.asyncio
class TestEnrichWithUnread:
    async def test_empty_tickets_no_query(self) -> None:
        """Ранний выход для пустого списка — без запроса к БД (экономия)."""
        db = AsyncMock()
        db.execute = AsyncMock()

        result = await reads_svc.enrich_with_unread(db, tickets=[], user_id=USER_ID)

        assert result == {}
        db.execute.assert_not_awaited()

    async def test_returns_map_for_all_tickets(self) -> None:
        """Map содержит ВСЕ входные ``ticket_id`` — даже прочитанные (False).

        Сериализатор делает ``map[t.id]`` без обработки KeyError — это контракт.
        """
        t1 = _ticket(id_=TICKET_ID)
        t2 = _ticket(id_=TICKET_ID_2)
        # БД вернула только t1 как непрочитанный (t2 прочитан / нет inbound).
        db = _make_db(
            [_result(rows=[(TICKET_ID, 3)])]  # (ticket_id, unread_count)
        )

        result = await reads_svc.enrich_with_unread(db, tickets=[t1, t2], user_id=USER_ID)

        assert set(result.keys()) == {TICKET_ID, TICKET_ID_2}
        assert result[TICKET_ID] is True
        assert result[TICKET_ID_2] is False

    async def test_single_query_for_whole_list(self) -> None:
        """Критично: один запрос на весь список (а не N+1 по тикетам)."""
        tickets = [_ticket() for _ in range(20)]
        db = _make_db([_result(rows=[])])

        await reads_svc.enrich_with_unread(db, tickets=tickets, user_id=USER_ID)

        assert db.execute.await_count == 1

    async def test_all_unread(self) -> None:
        """Все тикеты имеют новые сообщения → все True."""
        t1 = _ticket(id_=TICKET_ID)
        t2 = _ticket(id_=TICKET_ID_2)
        db = _make_db([_result(rows=[(TICKET_ID, 1), (TICKET_ID_2, 2)])])

        result = await reads_svc.enrich_with_unread(db, tickets=[t1, t2], user_id=USER_ID)

        assert result == {TICKET_ID: True, TICKET_ID_2: True}

    async def test_no_commit(self) -> None:
        """Read-only запрос — ``db.commit`` не нужен (как в list-endpoints)."""
        t1 = _ticket(id_=TICKET_ID)
        db = _make_db([_result(rows=[])])
        await reads_svc.enrich_with_unread(db, tickets=[t1], user_id=USER_ID)
        db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestUnreadDirectionParameterization:
    """Параметризация ``direction`` (агентский inbound vs заявительский outbound).

    Фикс: ``reads.py`` раньше был захардкожен на ``direction='inbound'`` (только
    для агентов — ответы заявителя). Теперь параметр опциональный, и для
    заявителя передаётся ``direction='outbound'`` (ответы агентов).
    """

    async def test_default_direction_is_inbound(self) -> None:
        """Без явного direction используется ``inbound`` (агентский путь).

        Регресс: существующий агентский вызов не должен сломаться.
        """
        db = _make_db([_result(scalar=True)])
        result = await reads_svc.has_unread_requester_messages(
            db, ticket_id=TICKET_ID, user_id=USER_ID
        )
        assert result is True

    async def test_explicit_inbound_direction(self) -> None:
        """Явный ``direction='inbound'`` — то же, что дефолт (регресс агентов)."""
        db = _make_db([_result(scalar=True)])
        result = await reads_svc.has_unread_requester_messages(
            db, ticket_id=TICKET_ID, user_id=USER_ID, direction="inbound"
        )
        assert result is True

    async def test_outbound_direction_for_requester(self) -> None:
        """``direction='outbound'`` — заявительский контракт (ответы агентов).

        Структурно: функция принимает direction, передаёт в SQL WHERE.
        На unit-уровне (с мок-БД) проверяем только что вызов проходит без
        ошибки — семантика inbound/outbound проверяется в integration-тестах.
        """
        db = _make_db([_result(scalar=False)])
        result = await reads_svc.has_unread_requester_messages(
            db, ticket_id=TICKET_ID, user_id=USER_ID, direction="outbound"
        )
        assert result is False

    async def test_enrich_accepts_outbound_direction(self) -> None:
        """``enrich_with_unread(direction='outbound')`` — для заявительского списка."""
        t1 = _ticket(id_=TICKET_ID)
        db = _make_db([_result(rows=[(TICKET_ID, 1)])])
        result = await reads_svc.enrich_with_unread(
            db, tickets=[t1], user_id=USER_ID, direction="outbound"
        )
        assert result == {TICKET_ID: True}

    async def test_enrich_default_direction_inbound(self) -> None:
        """Дефолт ``enrich_with_unread`` — ``inbound`` (регресс агентского пути)."""
        t1 = _ticket(id_=TICKET_ID)
        db = _make_db([_result(rows=[])])
        result = await reads_svc.enrich_with_unread(db, tickets=[t1], user_id=USER_ID)
        assert result == {TICKET_ID: False}
