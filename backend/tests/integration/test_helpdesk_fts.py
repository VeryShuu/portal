"""Integration tests — полнотекстовый поиск по тикетам helpdesk (FTS).

Проверяет замену ilike на websearch_to_tsquery (миграция 078):
* морфология (vpn → впн/vpn, регистронезависимость);
* операторы websearch: "точная фраза", OR, -исключение;
* поиск по subject+description тикета (search_tsvector);
* поиск по телам ответов (EXISTS по helpdesk_messages.body_tsvector);
* email через ilike (FTS его не матчит);
* комбинация FTS + status-фильтр.

Требует INTEGRATION_DB=true (нужна реальная БД с russian_hunspell и применённой
миграцией 078). Авто-skip'ается иначе.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket
from app.services.helpdesk.tickets import _agent_filter_conditions

pytestmark = pytest.mark.asyncio


# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_ticket(
    *,
    subject: str,
    description: str = "",
    status: str = "new",
    requester_email: str = "user@portal.local",
) -> HelpdeskTicket:
    """Создать HelpdeskTicket для FTS-теста.

    ``number`` намеренно НЕ передаётся — колонка объявлена как
    ``GENERATED ALWAYS AS IDENTITY`` (миграция 075), и явный INSERT значения
    без ``OVERRIDING SYSTEM VALUE`` падает с ``cannot insert a non-DEFAULT value``.
    IDENTITY сам сгенерирует number; всем assertion'ам теста нужен только ``id``,
    который выдаётся ``gen_random_uuid()`` ещё до flush."""
    return HelpdeskTicket(
        subject=subject,
        description=description,
        description_html=None,
        status=status,
        source="web",
        requester_email=requester_email,
        requester_name="Тест",
        last_activity_at=datetime.now(UTC),
    )


def _make_message(
    *,
    ticket_id: uuid.UUID,
    body_text: str,
    direction: str = "inbound",
    visibility: str = "public",
) -> HelpdeskMessage:
    return HelpdeskMessage(
        ticket_id=ticket_id,
        author_email="user@portal.local",
        author_name="Тест",
        direction=direction,
        visibility=visibility,
        body_text=body_text,
        source="web",
    )


async def _fetch_matched_ids(db, query: str) -> set[uuid.UUID]:
    """Прогнать _agent_filter_conditions с query и вернуть id матченных тикетов."""
    conditions = _agent_filter_conditions(
        status_filter=None,
        assignee_id=None,
        unassigned=False,
        source=None,
        query=query,
    )
    res = await db.execute(select(HelpdeskTicket.id).where(*conditions))
    return {row[0] for row in res.all()}


# ─── tests: морфология и операторы ──────────────────────────────────────────


class TestFtsMorphology:
    async def test_russian_stemming_finds_word_forms(self, real_db_session):
        """hunspell/stemming: «доступ» находит «доступа»/«доступу»/«доступом»."""
        t1 = _make_ticket(subject="Запрос", description="Нужен доступ к системе")
        t2 = _make_ticket(subject="Запрос", description="Проблема с принтером")
        real_db_session.add_all([t1, t2])
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "доступ")
        assert t1.id in matched
        assert t2.id not in matched

    async def test_case_insensitive(self, real_db_session):
        """Регистронезависимый поиск."""
        t = _make_ticket(subject="Ошибка VPN подключения")
        real_db_session.add(t)
        await real_db_session.flush()

        matched_lower = await _fetch_matched_ids(real_db_session, "vpn")
        matched_upper = await _fetch_matched_ids(real_db_session, "VPN")
        assert t.id in matched_lower
        assert t.id in matched_upper

    async def test_latin_in_russian_text(self, real_db_session):
        """Латинские термины в русском тексте ищутся (VPN, Office, Outlook)."""
        t = _make_ticket(
            subject="Помощь",
            description="Не работает Outlook, письма не приходят",
        )
        real_db_session.add(t)
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "outlook")
        assert t.id in matched


class TestFtsOperators:
    async def test_phrase_search(self, real_db_session):
        """Оператор "точная фраза" — матчится только как цельная фраза."""
        t1 = _make_ticket(
            subject="Сброс пароля",
            description="Нужно сбросить пароль учетной записи",
        )
        t2 = _make_ticket(
            subject="Другое",
            description="пароль был изменён ранее, нужен сброс учётки",
        )
        real_db_session.add_all([t1, t2])
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, '"сброс пароля"')
        assert t1.id in matched
        assert t2.id not in matched  # слова в другом порядке — не фраза

    async def test_or_operator(self, real_db_session):
        """OR — матчит любое из слов."""
        t1 = _make_ticket(subject="Принтер", description="не печатает")
        t2 = _make_ticket(subject="Сканер", description="не сканирует")
        real_db_session.add_all([t1, t2])
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "принтер OR сканер")
        assert t1.id in matched
        assert t2.id in matched

    async def test_exclude_operator(self, real_db_session):
        """Минус-исключение: слово после - исключает тикет с ним."""
        t1 = _make_ticket(subject="Доступ", description="к базе данных")
        t2 = _make_ticket(subject="Доступ", description="к базе данных отключён временно")
        real_db_session.add_all([t1, t2])
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "доступ -временно")
        assert t1.id in matched
        assert t2.id not in matched


# ─── tests: поиск по ответам (messages) ──────────────────────────────────────


class TestFtsSearchInReplies:
    async def test_finds_ticket_by_reply_body(self, real_db_session):
        """Тело ответа в helpdesk_messages находится, даже если в subject/
        description тикета слова нет — EXISTS по messages.body_tsvector."""
        t = _make_ticket(
            subject="Помощь",
            description="Нужна консультация",
        )
        real_db_session.add(t)
        await real_db_session.flush()
        real_db_session.add(_make_message(ticket_id=t.id, body_text="Настройте VPN по инструкции"))
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "vpn")
        assert t.id in matched

    async def test_internal_note_is_searched(self, real_db_session):
        """Internal-заметки (visibility=internal) тоже участвуют в поиске —
        агент должен находить свои внутренние комментарии."""
        t = _make_ticket(subject="Заявка", description="что-то")
        real_db_session.add(t)
        await real_db_session.flush()
        real_db_session.add(
            _make_message(
                ticket_id=t.id,
                body_text="Согласовать с руководителем отдела",
                visibility="internal",
                direction="outbound",
            )
        )
        await real_db_session.flush()

        matched = await _fetch_matched_ids(real_db_session, "руководитель")
        assert t.id in matched


# ─── tests: email через ilike ──────────────────────────────────────────────


class TestEmailIlike:
    async def test_email_matched_via_ilike(self, real_db_session):
        """Email заявителя ищется через ilike (FTS адреса не матчит — @/точки)."""
        t = _make_ticket(
            subject="Заявка",
            description="текст",
            requester_email="borisov.vs@company.local",
        )
        real_db_session.add(t)
        await real_db_session.flush()

        # Частичный email.
        matched = await _fetch_matched_ids(real_db_session, "borisov")
        assert t.id in matched
        # Домен.
        matched_domain = await _fetch_matched_ids(real_db_session, "company.local")
        assert t.id in matched_domain


# ─── tests: комбинация с фильтрами ───────────────────────────────────────────


class TestFtsWithFilters:
    async def test_fts_combined_with_status(self, real_db_session):
        """FTS-матч + status-фильтр работают вместе (AND)."""
        t_open = _make_ticket(subject="VPN проблема", description="не подключается", status="open")
        t_closed = _make_ticket(
            subject="VPN проблема",
            description="решено ранее",
            status="closed",
        )
        real_db_session.add_all([t_open, t_closed])
        await real_db_session.flush()

        conditions = _agent_filter_conditions(
            status_filter="open",
            assignee_id=None,
            unassigned=False,
            source=None,
            query="vpn",
        )
        res = await real_db_session.execute(select(HelpdeskTicket.id).where(*conditions))
        matched = {row[0] for row in res.all()}
        assert t_open.id in matched
        assert t_closed.id not in matched

    async def test_empty_query_no_filter(self, real_db_session):
        """Пустой/whitespace query не добавляет FTS-условие — все тикеты видны."""
        t = _make_ticket(subject="Любая", description="тема")
        real_db_session.add(t)
        await real_db_session.flush()

        for q in (None, "", "   "):
            matched = await _fetch_matched_ids(real_db_session, q)  # type: ignore[arg-type]
            assert t.id in matched  # нет фильтра → тикет в выдаче
