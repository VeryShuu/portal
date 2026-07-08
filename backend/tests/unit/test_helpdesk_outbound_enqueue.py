"""Unit-тесты ``enqueue_reply_outbound`` — формирование исходящего письма с историей.

Проверяет, что письмо заявителю включает: ответ агента + reply-маркер + историю
переписки (под маркером). ``enqueue_outbox_email`` мокается (паттерн
``test_news_email_share``), ``db`` — заглушка с AsyncMock для ``execute``.

Промышленный стандарт helpdesk (Zammad/Freshdesk): история под reply-маркером
даёт заявителю контекст, а при его ответе ``strip_quoted_reply`` режет по
``REPLY_MARKER_TOKEN`` → в ленте портала остаётся только чистый ответ.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.email_quote import REPLY_MARKER_TOKEN
from app.services.helpdesk.outbound import enqueue_reply_outbound


def _msg(
    *,
    text: str = "Предыдущее сообщение заявителя",
    direction: str = "inbound",
    visibility: str = "public",
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text=text,
        body_html=None,
        direction=direction,
        visibility=visibility,
        author_name="Заявитель",
        author_email="client@company.local",
        created_at=created_at or datetime(2026, 6, 30, 10, 0),
        email_message_id=f"<prev-{uuid.uuid4().hex[:8]}@company.local>",
    )


def _current_message() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text="Ответ агентa.",
        body_html="<p>Ответ агентa.</p>",
        direction="outbound",
        visibility="public",
        author_name="Агент",
        author_email="portal@company.local",
        created_at=datetime(2026, 7, 1, 12, 0),
        email_message_id="<tkn-5-curr@company.local>",
        author_user_id=uuid.uuid4(),
    )


def _ticket(*, messages: list, number: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        subject="Тема заявки",
        requester_email="client@company.local",
        messages=messages,
    )


def _mailbox() -> SimpleNamespace:
    return SimpleNamespace(
        support_address="portal@company.local",
    )


def _make_db() -> MagicMock:
    """Заглушка ``AsyncSession``: ``await db.execute(...)`` → объект с
    ``.scalars().all() == []`` (нет доп. references/вложений). ``commit`` —
    AsyncMock. ``execute`` — AsyncMock, его ``return_value`` — это то, что
    возвращает ``await db.execute(...)``."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
class TestTryEnqueueOutbound:
    async def test_email_contains_reply_then_marker_then_history(self) -> None:
        """Тело письма: ответ агента → reply-маркер → история. Маркер МЕЖДУ ними
        — точка отсечения при ответе заявителя."""
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=ticket, message=current, mailbox=_mailbox()
            )

        kwargs = enqueue.await_args.kwargs
        body_text = kwargs["body_text"]
        # Порядок: ответ → маркер → история (plain-цитатник «=== История заявки ===»).
        assert body_text.index("Ответ агентa.") < body_text.index(REPLY_MARKER_TOKEN)
        assert body_text.index(REPLY_MARKER_TOKEN) < body_text.index("История заявки")
        # История содержит предшествующее сообщение.
        assert "Предыдущее сообщение заявителя" in body_text

    async def test_html_body_has_history_under_marker(self) -> None:
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=ticket, message=current, mailbox=_mailbox()
            )

        body_html = enqueue.await_args.kwargs["body_html"]
        assert REPLY_MARKER_TOKEN in body_html
        assert body_html.index("Ответ агентa.") < body_html.index(REPLY_MARKER_TOKEN)
        # Шаблонный заголовок секции истории.
        assert "Предыдущие сообщения" in body_html

    async def test_no_history_for_first_reply(self) -> None:
        """Первый ответ агента (нет предшественников) — истории нет, разделитель
        не добавляется. Тело = шапка шаблона + ответ (без маркера)."""
        current = _current_message()
        ticket = _ticket(messages=[])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=ticket, message=current, mailbox=_mailbox()
            )

        body_text = enqueue.await_args.kwargs["body_text"]
        body_html = enqueue.await_args.kwargs["body_html"]
        assert "История заявки" not in body_text
        assert "Предыдущие сообщения" not in body_html
        assert "Ответ агентa." in body_text
        # Без истории — reply-маркер не ставится (точка отсечения не нужна).
        assert REPLY_MARKER_TOKEN not in body_text
        assert REPLY_MARKER_TOKEN not in body_html

    async def test_internal_notes_excluded_from_history(self) -> None:
        """Internal-заметки не попадают в исходящее письмо заявителю."""
        note = _msg(text="Секретная заметка", visibility="internal")
        prior = _msg(text="Публичный вопрос")
        current = _current_message()
        ticket = _ticket(messages=[note, prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=ticket, message=current, mailbox=_mailbox()
            )

        body_text = enqueue.await_args.kwargs["body_text"]
        assert "Секретная заметка" not in body_text
        assert "Публичный вопрос" in body_text

    async def test_subject_and_to_email(self) -> None:
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=ticket, message=current, mailbox=_mailbox()
            )

        kwargs = enqueue.await_args.kwargs
        assert kwargs["to_email"] == "client@company.local"
        assert kwargs["subject"] == "[#TKT-5] Тема заявки"
        assert kwargs["kind"] == "helpdesk"
