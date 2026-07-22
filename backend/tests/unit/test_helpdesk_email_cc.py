"""Unit-тесты email Cc в helpdesk — «ответить всем» (миграция 083).

Четыре зоны проверки:
1. ``threading.extract_cc`` — парсинг заголовка ``Cc`` входящего письма.
2. ``outbound.enqueue_reply_outbound`` — Cc проходит в ``payload["cc"]`` и
   санитизируется (CRLF-injection).
3. ``worker.email_outbox._apply_helpdesk_headers`` / ``_format_cc_header`` —
   заголовок ``Cc`` в MIME.
4. ``api.helpdesk._common._collect_participants`` — агрегация участников тикета.
5. ``api.helpdesk.tickets._normalize_cc_emails`` — нормализация Form-поля ``cc``.

Чистые функции — без БД (кроме outbound, где ``enqueue_outbox_email`` мокается,
как в ``test_helpdesk_outbound_enqueue.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from email.message import Message
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# 1. threading.extract_cc
# ──────────────────────────────────────────────────────────────────────────────
from app.services.helpdesk.threading import extract_cc


def _msg(headers: dict[str, str]) -> Message:
    m = Message()
    for k, v in headers.items():
        m[k] = v
    return m


class TestExtractCc:
    def test_single_address(self) -> None:
        out = extract_cc(_msg({"Cc": "colleague@company.local"}))
        assert out == [{"email": "colleague@company.local", "name": None}]

    def test_name_and_address(self) -> None:
        out = extract_cc(_msg({"Cc": "Иван Петров <ivan@company.local>"}))
        assert out == [{"email": "ivan@company.local", "name": "Иван Петров"}]

    def test_multiple_addresses(self) -> None:
        msg = _msg({"Cc": "a@x.local, b@y.local"})
        assert extract_cc(msg) == [
            {"email": "a@x.local", "name": None},
            {"email": "b@y.local", "name": None},
        ]

    def test_lowercased_and_deduplicated(self) -> None:
        # Повтор (в разном регистре) → дедупликация по lowercased email.
        msg = _msg({"Cc": "A@X.local, a@x.local, B@y.local"})
        assert extract_cc(msg) == [
            {"email": "a@x.local", "name": None},
            {"email": "b@y.local", "name": None},
        ]

    def test_rfc2047_encoded_name(self) -> None:
        # Кириллическое имя в RFC 2047 (как Subject/From) — декодируется.
        out = extract_cc(_msg({"Cc": "=?utf-8?B?0KLQuNCy0LXRgg==?= <a@x.local>"}))
        assert out == [{"email": "a@x.local", "name": "Тивет"}]

    def test_excludes_support_address(self) -> None:
        # support_address выкидывается (петля) — case-insensitive.
        msg = _msg({"Cc": "support@company.local, other@x.local"})
        out = extract_cc(msg, exclude="Support@Company.Local")
        assert out == [{"email": "other@x.local", "name": None}]

    def test_no_cc_header(self) -> None:
        assert extract_cc(_msg({})) == []

    def test_empty_cc(self) -> None:
        assert extract_cc(_msg({"Cc": ""})) == []

    def test_invalid_entries_skipped(self) -> None:
        # Без @, пустые — пропускаются.
        msg = _msg({"Cc": "notanemail, , valid@x.local"})
        assert extract_cc(msg) == [{"email": "valid@x.local", "name": None}]

    def test_order_preserved(self) -> None:
        # Порядок как в письме (важно для «ответить всем» — получатель видит
        # привычный порядок адресатов).
        msg = _msg({"Cc": "z@x.local, a@x.local, m@x.local"})
        emails = [p["email"] for p in extract_cc(msg)]
        assert emails == ["z@x.local", "a@x.local", "m@x.local"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. outbound.enqueue_reply_outbound — payload["cc"]
# ──────────────────────────────────────────────────────────────────────────────

from app.services.helpdesk.outbound import enqueue_reply_outbound


def _cc_msg(
    *,
    text: str = "Ответ заявителя",
    cc: list[dict] | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text=text,
        body_html=None,
        direction="outbound",
        visibility="public",
        author_name="Агент",
        author_email="portal@company.local",
        author_user_id=uuid.uuid4(),
        created_at=datetime(2026, 7, 22, 12, 0),
        email_message_id=f"<tkn-5-{uuid.uuid4().hex[:8]}@company.local>",
        attachments=[],
        cc=cc,
    )


def _cc_ticket() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=5,
        subject="Тема",
        requester_email="client@company.local",
        messages=[],
        assignee_user_id=None,
    )


def _cc_mailbox() -> Any:
    return SimpleNamespace(
        support_address="portal@company.local",
        support_reply_to=None,
    )


def _cc_db() -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
class TestEnqueueReplyOutboundCc:
    async def test_cc_in_payload(self) -> None:
        cc = [
            {"email": "a@x.local", "name": "Иван"},
            {"email": "b@y.local", "name": None},
        ]
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                _cc_db(),
                ticket=_cc_ticket(),
                message=_cc_msg(cc=cc),
                mailbox=_cc_mailbox(),
            )
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["cc"] == cc

    async def test_no_cc_empty_list_in_payload(self) -> None:
        # message.cc = None → payload["cc"] = [] (нормализованный пустой список,
        # не None —worker'у проще).
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                _cc_db(),
                ticket=_cc_ticket(),
                message=_cc_msg(cc=None),
                mailbox=_cc_mailbox(),
            )
        payload = enqueue.await_args.kwargs["payload"]
        assert payload["cc"] == []

    async def test_cc_crlf_stripped(self) -> None:
        """H-4: CRLF в email/name Cc не должен инжектить заголовки. Каждый
        адрес проходит ``_sanitize_header_field`` (как ``to_email``/``subject``).
        """
        cc = [
            {"email": "a@x.local\r\nBcc: leak@evil.test", "name": "И"},
            {"name": "Name\nX-Inject: yes", "email": "b@y.local"},
        ]
        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                _cc_db(),
                ticket=_cc_ticket(),
                message=_cc_msg(cc=cc),
                mailbox=_cc_mailbox(),
            )
        payload = enqueue.await_args.kwargs["payload"]
        for p in payload["cc"]:
            assert "\r" not in p["email"], p
            assert "\n" not in p["email"], p
            assert p["name"] is None or ("\r" not in p["name"] and "\n" not in p["name"]), p


# ──────────────────────────────────────────────────────────────────────────────
# 3. worker email_outbox — заголовок Cc
# ──────────────────────────────────────────────────────────────────────────────

from app.worker.tasks.email_outbox import _apply_helpdesk_headers, _format_cc_header


class TestFormatCcHeader:
    def test_empty_list(self) -> None:
        assert _format_cc_header([]) == ""

    def test_bare_emails(self) -> None:
        out = _format_cc_header(
            [{"email": "a@x.local", "name": None}, {"email": "b@y.local", "name": None}]
        )
        assert "a@x.local" in out
        assert "b@y.local" in out

    def test_names_via_formataddr(self) -> None:
        out = _format_cc_header([{"email": "a@x.local", "name": "Иван"}])
        # formataddr кодирует не-ASCII имя в RFC 2047 (=?utf-8?b?...?=) —
        # корректно для заголовка. Проверяем адрес + декодированное имя.
        assert "a@x.local" in out
        from email.header import decode_header, make_header

        decoded = str(make_header(decode_header(out)))
        assert "Иван" in decoded

    def test_skips_invalid_entries(self) -> None:
        out = _format_cc_header(
            [{"email": "a@x.local", "name": None}, {"email": "", "name": None}, "not-a-dict"]
        )
        assert "a@x.local" in out
        # Только один валидный адрес.
        assert out.count("@") == 1


class TestApplyHeadersCc:
    def _outer(self) -> Any:
        from email.mime.multipart import MIMEMultipart

        return MIMEMultipart("mixed")

    def test_cc_header_set_when_present(self) -> None:
        outer = self._outer()
        _apply_helpdesk_headers(
            outer,
            subject="s",
            from_address="portal@company.local",
            to_email="client@company.local",
            reply_to_address="portal@company.local",
            payload={"cc": [{"email": "a@x.local", "name": None}]},
        )
        assert outer["Cc"] is not None
        assert "a@x.local" in outer["Cc"]

    def test_no_cc_header_when_empty(self) -> None:
        outer = self._outer()
        _apply_helpdesk_headers(
            outer,
            subject="s",
            from_address="portal@company.local",
            to_email="client@company.local",
            reply_to_address="portal@company.local",
            payload={},
        )
        assert outer.get("Cc") is None

    def test_cc_crlf_stripped_in_header(self) -> None:
        """Defense-in-depth: даже если в payload попал CRLF (БД отредактирована
        вручную), worker стрипает его повторно (как Subject/To)."""
        outer = self._outer()
        _apply_helpdesk_headers(
            outer,
            subject="s",
            from_address="portal@company.local",
            to_email="client@company.local",
            reply_to_address="portal@company.local",
            payload={"cc": [{"email": "a@x.local\r\nBcc: leak@evil", "name": "N\r\nX: y"}]},
        )
        cc_val = outer["Cc"]
        assert "\r" not in cc_val
        assert "\n" not in cc_val
        # Сам Bcc-injection не должен появиться как отдельный заголовок.
        assert outer.get("Bcc") is None


# ──────────────────────────────────────────────────────────────────────────────
# 4. _common._collect_participants — агрегация участников
# ──────────────────────────────────────────────────────────────────────────────

from app.api.helpdesk._common import _collect_participants, message_to_out


def _ticket_msg(
    *,
    direction: str = "inbound",
    author_email: str = "client@company.local",
    author_name: str | None = "Заявитель",
    cc: list[dict] | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        direction=direction,
        visibility="public",
        source="email",
        author_email=author_email,
        author_name=author_name,
        author_user_id=None,
        body_text="текст",
        body_html=None,
        attachments=[],
        cc=cc,
        created_at=datetime(2026, 7, 22, 10, 0),
    )


def _ticket_obj(
    *,
    requester_email: str = "client@company.local",
    requester_name: str | None = "Заявитель",
    messages: list[Any],
) -> Any:
    return SimpleNamespace(
        requester_email=requester_email,
        requester_name=requester_name,
        messages=messages,
    )


class TestCollectParticipants:
    def test_requester_first_and_marked(self) -> None:
        ticket = _ticket_obj(messages=[_ticket_msg(cc=[{"email": "a@x.local", "name": None}])])
        out = _collect_participants(ticket, requester_email=ticket.requester_email)
        assert out[0].email == "client@company.local"
        assert out[0].is_requester is True
        # Cc добавлен, не requester.
        assert any(p.email == "a@x.local" and not p.is_requester for p in out)

    def test_dedup_across_messages_and_cc(self) -> None:
        # Один адрес в Cc одного сообщения и author_email другого —
        # должен появиться один раз.
        ticket = _ticket_obj(
            messages=[
                _ticket_msg(cc=[{"email": "a@x.local", "name": None}]),
                _ticket_msg(author_email="a@x.local", author_name="Иван"),
            ]
        )
        out = _collect_participants(ticket, requester_email=ticket.requester_email)
        a_count = sum(1 for p in out if p.email == "a@x.local")
        assert a_count == 1
        # Requester + a@x.local = 2 участника.
        assert len(out) == 2

    def test_requester_not_duplicated_when_also_cc(self) -> None:
        # Если requester почему-то оказался в Cc письма (отправил себе копию) —
        # не дублируем: он уже в To как requester.
        ticket = _ticket_obj(
            messages=[_ticket_msg(cc=[{"email": "client@company.local", "name": None}])]
        )
        out = _collect_participants(ticket, requester_email=ticket.requester_email)
        assert len(out) == 1
        assert out[0].email == "client@company.local"
        assert out[0].is_requester is True

    def test_no_messages_just_requester(self) -> None:
        ticket = _ticket_obj(messages=[])
        out = _collect_participants(ticket, requester_email=ticket.requester_email)
        assert len(out) == 1
        assert out[0].is_requester is True

    def test_message_to_out_includes_cc(self) -> None:
        msg = _ticket_msg(cc=[{"email": "a@x.local", "name": "Иван"}])
        out = message_to_out(msg)
        assert len(out.cc) == 1
        assert out.cc[0].email == "a@x.local"
        assert out.cc[0].name == "Иван"

    def test_message_to_out_no_cc_empty(self) -> None:
        msg = _ticket_msg(cc=None)
        assert message_to_out(msg).cc == []


# ──────────────────────────────────────────────────────────────────────────────
# 5. router _normalize_cc_emails
# ──────────────────────────────────────────────────────────────────────────────

from app.api.helpdesk.tickets import _normalize_cc_emails


class TestNormalizeCcEmails:
    def test_basic(self) -> None:
        out = _normalize_cc_emails(
            ["a@x.local", "b@y.local"],
            exclude=set(),
            support_address=None,
        )
        assert out == [
            {"email": "a@x.local", "name": None},
            {"email": "b@y.local", "name": None},
        ]

    def test_lowercases(self) -> None:
        out = _normalize_cc_emails(["A@X.LOCAL"], exclude=set(), support_address=None)
        assert out == [{"email": "a@x.local", "name": None}]

    def test_strips_name_from_angle_form(self) -> None:
        # "Иван <a@x.local>" → только адрес.
        out = _normalize_cc_emails(["Иван <a@x.local>"], exclude=set(), support_address=None)
        assert out == [{"email": "a@x.local", "name": None}]

    def test_excludes_requester_and_agent(self) -> None:
        out = _normalize_cc_emails(
            ["agent@company.local", "client@company.local", "other@x.local"],
            exclude={"agent@company.local", "client@company.local"},
            support_address=None,
        )
        assert out == [{"email": "other@x.local", "name": None}]

    def test_excludes_support_address(self) -> None:
        out = _normalize_cc_emails(
            ["support@company.local", "other@x.local"],
            exclude=set(),
            support_address="support@company.local",
        )
        assert out == [{"email": "other@x.local", "name": None}]

    def test_deduplicates(self) -> None:
        out = _normalize_cc_emails(
            ["a@x.local", "A@X.local", "a@x.local"],
            exclude=set(),
            support_address=None,
        )
        assert out == [{"email": "a@x.local", "name": None}]

    def test_skips_invalid(self) -> None:
        out = _normalize_cc_emails(
            ["", "notanemail", "a@x.local"],
            exclude=set(),
            support_address=None,
        )
        assert out == [{"email": "a@x.local", "name": None}]

    def test_empty_input(self) -> None:
        assert _normalize_cc_emails([], exclude=set(), support_address=None) == []

    def test_limit_exceeded_raises(self) -> None:
        from fastapi import HTTPException

        many = [f"u{i}@x.local" for i in range(21)]
        with pytest.raises(HTTPException) as exc_info:
            _normalize_cc_emails(many, exclude=set(), support_address=None)
        assert exc_info.value.status_code == 422
