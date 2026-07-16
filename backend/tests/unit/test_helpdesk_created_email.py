"""Unit-тесты письма-подтверждения заявителю «заявка зарегистрирована».

Письмо инициатору при создании заявки (web-форма или IMAP-ingress): номер
заявки, обращение принято, свяжется специалист, инструкция для ответа.
Тикет-токен ``[#TKT-{number}]`` в теме — для Subject-matching входящих ответов.

Покрывает:
* чистые функции ``build_created_email_*`` (subject + bodies) — без БД;
* ``enqueue_created_email`` — payload, threading-заголовки (``kind=helpdesk``,
  ``Message-ID`` корень треда, пустой ``references``/``in_reply_to``);
* ``_try_enqueue_created_email`` — best-effort (нет mailbox → no-op).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.helpdesk import HelpdeskTicket
from app.services.helpdesk.notifications import (
    build_created_email_bodies,
    build_created_email_subject,
)
from app.services.helpdesk.outbound import enqueue_created_email


def _ticket(*, number: int = 42, subject: str = "Не работает VPN") -> HelpdeskTicket:
    return HelpdeskTicket(
        id=uuid.uuid4(),
        subject=subject,
        description="описание",
        status="new",
        source="web",
        requester_email="user@portal.local",
        requester_name="User",
        number=number,
        created_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )


def _mailbox() -> SimpleNamespace:
    return SimpleNamespace(support_address="support@company.local")


# ── Subject ──────────────────────────────────────────────────────────────────


class TestCreatedEmailSubject:
    def test_subject_has_ticket_token(self) -> None:
        subject = build_created_email_subject(_ticket(number=42))
        assert subject.startswith("[#TKT-42] ")

    def test_subject_says_registered(self) -> None:
        subject = build_created_email_subject(_ticket())
        assert "Заявка зарегистрирована" in subject

    def test_subject_independent_of_ticket_subject(self) -> None:
        """Тема письма — фиксированная, не дублирует тему заявки (тема заявки
        уже в шапке письма, а в Subject-токене достаточно для matching)."""
        subject = build_created_email_subject(_ticket(subject="Что-то случилось"))
        assert "Что-то случилось" not in subject


# ── Bodies ───────────────────────────────────────────────────────────────────


class TestCreatedEmailBodies:
    def test_plain_announces_registration(self) -> None:
        _html, plain = build_created_email_bodies(_ticket(number=42))
        assert "принята и зарегистрирована" in plain
        assert "[#TKT-42]" in plain

    def test_plain_has_ticket_number(self) -> None:
        """Номер и тема приходят из шапки шаблона render_system_email."""
        _html, plain = build_created_email_bodies(_ticket(number=42, subject="VPN"))
        assert "TKT-42" in plain
        assert "VPN" in plain

    def test_plain_mentions_specialist(self) -> None:
        _html, plain = build_created_email_bodies(_ticket())
        assert "специалист" in plain.lower()

    def test_plain_has_reply_hint_with_token(self) -> None:
        _html, plain = build_created_email_bodies(_ticket(number=7))
        # Ответ заявителя должен сохранить токен в теме.
        assert "[#TKT-7]" in plain

    def test_html_escapes_subject(self) -> None:
        """XSS-защита: тема с HTML-спецсимволами экранируется."""
        html_body, _plain = build_created_email_bodies(
            _ticket(number=1, subject="<script>alert(1)</script>")
        )
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_html_contains_number_and_token(self) -> None:
        html_body, _plain = build_created_email_bodies(_ticket(number=42))
        assert "TKT-42" in html_body
        assert "[#TKT-42]" in html_body

    def test_returns_html_plain_tuple(self) -> None:
        result = build_created_email_bodies(_ticket())
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)


# ── enqueue_created_email ────────────────────────────────────────────────────


def _make_db() -> MagicMock:
    """Заглушка ``AsyncSession`` для enqueue (``collect_ticket_references``
    возвращает пустой список — новый тикет, истории нет)."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


class TestEnqueueCreatedEmail:
    @pytest.mark.asyncio
    async def test_enqueues_to_requester_email(self) -> None:
        db = _make_db()
        ticket = _ticket()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=ticket, mailbox=_mailbox())
        assert enqueue.await_args.kwargs["to_email"] == ticket.requester_email

    @pytest.mark.asyncio
    async def test_uses_helpdesk_kind(self) -> None:
        """kind=helpdesk (не generic): письмо входит в email-тред тикета, несёт
        threading-заголовки — ответ заявителя вернётся в тикет."""
        db = _make_db()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=_ticket(), mailbox=_mailbox())
        assert enqueue.await_args.kwargs["kind"] == "helpdesk"

    @pytest.mark.asyncio
    async def test_subject_has_token_and_registered(self) -> None:
        db = _make_db()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=_ticket(number=99), mailbox=_mailbox())
        subject = enqueue.await_args.kwargs["subject"]
        assert "[#TKT-99]" in subject
        assert "Заявка зарегистрирована" in subject

    @pytest.mark.asyncio
    async def test_payload_empty_references_for_new_ticket(self) -> None:
        """Новый тикет — это корень треда: references пуст, in_reply_to=None.
        Message-ID этого письма станет ancestor'ом для будущих ответов."""
        db = _make_db()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=_ticket(), mailbox=_mailbox())
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["references"] == []
        assert payload["in_reply_to"] is None
        # Message-ID — корень треда в каноническом формате.
        assert payload["message_id_header"].startswith("<tkn-")
        assert "@" in payload["message_id_header"]

    @pytest.mark.asyncio
    async def test_payload_has_support_domain_and_reply_to(self) -> None:
        """Threading-данные для MIME-builder: support_domain (для msg-id),
        reply_to (адрес ящика, на который вернётся ответ заявителя)."""
        db = _make_db()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(
                db, ticket=_ticket(), mailbox=SimpleNamespace(support_address="help@x.test")
            )
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["support_domain"] == "x.test"
        assert payload["reply_to"] == "help@x.test"
        assert payload["support_address"] == "help@x.test"

    @pytest.mark.asyncio
    async def test_related_resource_is_ticket(self) -> None:
        db = _make_db()
        ticket = _ticket()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=ticket, mailbox=_mailbox())
        kwargs = enqueue.await_args.kwargs
        assert kwargs["related_resource_type"] == "helpdesk_ticket"
        assert kwargs["related_resource_id"] == ticket.id

    @pytest.mark.asyncio
    async def test_bodies_built_from_template(self) -> None:
        """Тела строятся через ``build_created_email_bodies`` — содержат номер и
        подтверждение регистрации."""
        db = _make_db()
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(
                db, ticket=_ticket(number=5, subject="Тест"), mailbox=_mailbox()
            )
        kwargs = enqueue.await_args.kwargs
        assert "TKT-5" in kwargs["body_text"]
        assert "регистрир" in kwargs["body_text"].lower()
        assert "TKT-5" in kwargs["body_html"]


# ── _try_enqueue_created_email (best-effort wrapper) ─────────────────────────


class TestTryEnqueueCreatedEmail:
    @pytest.mark.asyncio
    async def test_noop_without_mailbox(self) -> None:
        """Нет mailbox → no-op (web-only helpdesk): заявку можно создать, но
        подтверждение на email не уходит."""
        from app.services.helpdesk.tickets import _try_enqueue_created_email

        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.one_or_none.return_value = None  # нет mailbox
        db.execute = AsyncMock(return_value=result)
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await _try_enqueue_created_email(db, ticket=_ticket())
        enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueues_with_mailbox(self) -> None:
        from app.services.helpdesk.tickets import _try_enqueue_created_email

        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.one_or_none.return_value = _mailbox()
        db.execute = AsyncMock(return_value=result)
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await _try_enqueue_created_email(db, ticket=_ticket())
        enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_swallows_exception(self) -> None:
        """Сбой enqueue не роняет создание заявки (best-effort, лог warning)."""
        from app.services.helpdesk.tickets import _try_enqueue_created_email

        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.one_or_none.return_value = _mailbox()
        db.execute = AsyncMock(return_value=result)
        with (
            patch(
                "app.services.helpdesk.outbound.enqueue_outbox_email",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch("app.services.helpdesk.tickets.logger") as mock_logger,
        ):
            # Не должно пробросить исключение.
            await _try_enqueue_created_email(db, ticket=_ticket())
        mock_logger.warning.assert_called_once()
