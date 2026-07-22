"""Unit-тесты ``enqueue_reply_outbound`` — формирование исходящего письма с историей.

Проверяет, что письмо заявителю включает: ответ агента + историю переписки.
``enqueue_outbox_email`` мокается (паттерн ``test_news_email_share``), ``db`` —
заглушка с AsyncMock для ``execute``.

Reply-маркер («Ответьте выше этой линии») НЕ ставится: отсечение цитат при
ответе заявителя работает по заголовкам почтового клиента (Outlook ``From:/Sent:``,
Gmail ``wrote:``) через ``strip_quoted_reply``/``strip_quoted_html`` — как в OTRS.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.email_quote import REPLY_MARKER_TOKEN
from app.services.helpdesk.outbound import enqueue_reply_outbound


def _msg(
    *,
    text: str = "Предыдущее сообщение заявителя",
    direction: str = "inbound",
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text=text,
        body_html=None,
        direction=direction,
        author_name="Заявитель",
        author_email="client@company.local",
        created_at=created_at or datetime(2026, 6, 30, 10, 0),
        email_message_id=f"<prev-{uuid.uuid4().hex[:8]}@company.local>",
    )


def _current_message() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text="Ответ агентa.",
        body_html="<p>Ответ агентa.</p>",
        direction="outbound",
        author_name="Агент",
        author_email="portal@company.local",
        created_at=datetime(2026, 7, 1, 12, 0),
        email_message_id="<tkn-5-curr@company.local>",
        author_user_id=uuid.uuid4(),
    )


def _ticket(*, messages: list, number: int = 5) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        subject="Тема заявки",
        requester_email="client@company.local",
        messages=messages,
    )


def _mailbox() -> Any:
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
    async def test_email_contains_reply_then_history(self) -> None:
        """Тело письма: ответ агента → история (без reply-маркера — отсечение
        цитат по заголовкам почтового клиента, как в OTRS)."""
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        kwargs = enqueue.await_args.kwargs
        body_text = kwargs["body_text"]
        # Ответ → история (plain-цитатник «=== История заявки ===»). Reply-маркер
        # НЕ ставится (отсечение цитат — по заголовкам почтового клиента, как в OTRS).
        assert body_text.index("Ответ агентa.") < body_text.index("История заявки")
        assert REPLY_MARKER_TOKEN not in body_text
        # История содержит предшествующее сообщение.
        assert "Предыдущее сообщение заявителя" in body_text

    async def test_html_body_has_history_section(self) -> None:
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        body_html = enqueue.await_args.kwargs["body_html"]
        # Reply-маркера нет (отсечение — по эвристике, как в OTRS).
        assert REPLY_MARKER_TOKEN not in body_html
        assert "↩" not in body_html
        # Заголовка «Предыдущие сообщения» нет (убран по запросу).
        assert "Предыдущие сообщения" not in body_html
        # Ответ присутствует, история присутствует (разделяются <hr>).
        assert "Ответ агентa." in body_html
        assert "Предыдущее сообщение заявителя" in body_html

    async def test_no_history_for_first_reply(self) -> None:
        """Первый ответ агента (нет предшественников) — истории нет, разделитель
        не добавляется. Тело = шапка шаблона + ответ (без маркера)."""
        current = _current_message()
        ticket = _ticket(messages=[])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        body_text = enqueue.await_args.kwargs["body_text"]
        body_html = enqueue.await_args.kwargs["body_html"]
        assert "История заявки" not in body_text
        assert "Предыдущие сообщения" not in body_html
        assert "Ответ агентa." in body_text
        # Без истории — reply-маркер не ставится (точка отсечения не нужна).
        assert REPLY_MARKER_TOKEN not in body_text
        assert REPLY_MARKER_TOKEN not in body_html

    async def test_subject_and_to_email(self) -> None:
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        kwargs = enqueue.await_args.kwargs
        assert kwargs["to_email"] == "client@company.local"
        assert kwargs["subject"] == "[#TKT-5] Тема заявки"
        assert kwargs["kind"] == "helpdesk"

    async def test_header_injection_subject_stripped(self) -> None:
        """H-4: CRLF в ticket.subject не должен попадать в outbox subject.

        Заявитель присылает письмо с ``Subject: ...\\r\\nBcc: victim@x``.
        Defense-in-depth: outbox worker уже санизирует (E3), но продюсер тоже
        должен стрипать CRLF — на случай нового продюсера или изменения
        outbox-контракта. Без стрипа ``Subject: ...\\r\\nBcc:`` инжектит
        BCC-заголовок (фишинг с доверенного support-адреса).

        Key assertion: отсутствие CR/LF (именно newline делает MIME-header
        injection возможным). Текст 'Bcc:' без newline — безвредная часть
        значения темы, не отдельный заголовок."""
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        # \r\n + Bcc header injection в теме.
        ticket.subject = "Легитимная тема\r\nBcc: victim@evil.test"
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        subject = enqueue.await_args.kwargs["subject"]
        # CR/LF стрипнуты — MIME-header injection невозможен (newline — разделитель
        # заголовков в RFC 5322; без него 'Bcc:' остаётся частью значения Subject).
        assert "\r" not in subject, f"CRLF не стрипнут из subject: {subject!r}"
        assert "\n" not in subject, f"CRLF не стрипнут из subject: {subject!r}"

    async def test_header_injection_requester_email_stripped(self) -> None:
        """H-4: CRLF в requester_email не должен попадать в to_email.

        Guest-заявитель с email, содержащим newline (через подделанный From),
        не должен инжектить заголовки в исходящем письме. Key assertion —
        отсутствие CR/LF (см. тест subject)."""
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        ticket.requester_email = "client@company.local\r\nBcc: leak@evil.test"
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        to_email = enqueue.await_args.kwargs["to_email"]
        assert "\r" not in to_email, f"CRLF не стрипнут из to_email: {to_email!r}"
        assert "\n" not in to_email, f"CRLF не стрипнут из to_email: {to_email!r}"

    async def test_payload_subject_original_also_stripped(self) -> None:
        """H-4: ``subject_original`` в payload тоже санизируется — он попадает в
        БД (email_outbox.payload JSONB) и может переиспользоваться другим слоем."""
        prior = _msg()
        current = _current_message()
        ticket = _ticket(messages=[prior])
        ticket.subject = "Тема\r\nX-Injected: yes"
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        payload = enqueue.await_args.kwargs["payload"]
        subject_orig = payload["subject_original"]
        assert "\r" not in subject_orig and "\n" not in subject_orig

    async def test_plain_text_body_escaped_in_pre(self) -> None:
        """H-6: если агент отправил только plain-text (body_html пуст), body_text
        экранируется через _esc перед обёрткой в <pre> — иначе
        ``</pre><script>...`` в тексте агента инжектит HTML."""
        prior = _msg()
        # Сообщение с body_html=None и body_text с HTML-инъекцией.
        # Аннотация ``Any`` — иначе mypy ругается на SimpleNamespace вместо
        # HelpdeskMessage (сигнатура enqueue_reply_outbound). Как и в _msg() /
        # _current_message(), используем SimpleNamespace для минимальной заглушки
        # — тест проверяет escape-логику, а не модель.
        current: Any = SimpleNamespace(
            id=uuid.uuid4(),
            body_text="Текст </pre><script>alert(1)</script>",
            body_html=None,
            direction="outbound",
            author_name="Агент",
            author_email="portal@company.local",
            created_at=datetime(2026, 7, 1, 12, 0),
            email_message_id="<tkn-5-curr@company.local>",
            author_user_id=uuid.uuid4(),
        )
        ticket = _ticket(messages=[prior])
        db = _make_db()

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(db, ticket=ticket, message=current, mailbox=_mailbox())

        assert enqueue.await_args is not None
        body_html = enqueue.await_args.kwargs["body_html"]
        # Скрипт экранирован — не выполняется в письме.
        assert "<script>" not in body_html
        assert "&lt;script&gt;" in body_html
        # </pre> атакующего экранирован — не закрывает наш <pre> преждевременно.
        assert body_html.count("</pre>") <= 1  # только наш закрывающий (если есть)
