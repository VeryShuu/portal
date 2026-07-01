"""Unit-тесты email-threading helpers (Этап 5).

Чистые функции парсинга Message-ID/References/токена темы и normalisation
адреса — без БД и сети. См. ТЗ §1.3.8, §5.1.
"""

from __future__ import annotations

from email.message import Message

from app.services.helpdesk.threading import (
    decode_mime_header,
    extract_display_name,
    extract_message_id,
    extract_references,
    extract_subject_token,
    is_outbound_message_id,
    normalize_email,
    parse_outbound_message_id,
    synthetic_message_id,
)


def _msg(headers: dict[str, str]) -> Message:
    m = Message()
    for k, v in headers.items():
        m[k] = v
    return m


class TestExtractMessageId:
    def test_present(self) -> None:
        assert extract_message_id(_msg({"Message-ID": "<abc@host>"})) == "<abc@host>"

    def test_wraps_bare_id(self) -> None:
        assert extract_message_id(_msg({"Message-ID": "abc@host"})) == "<abc@host>"

    def test_missing(self) -> None:
        assert extract_message_id(_msg({})) is None

    def test_empty(self) -> None:
        assert extract_message_id(_msg({"Message-ID": "  "})) is None

    def test_takes_first_token(self) -> None:
        # Несколько токенов — берём первый.
        assert extract_message_id(_msg({"Message-ID": "<a@h> <b@h>"})) == "<a@h>"


class TestExtractReferences:
    def test_in_reply_to_and_references_deduped(self) -> None:
        refs = extract_references(_msg({"In-Reply-To": "<a@h>", "References": "<a@h> <b@h>"}))
        assert refs == ["<a@h>", "<b@h>"]

    def test_empty(self) -> None:
        assert extract_references(_msg({})) == []


class TestSubjectToken:
    def test_found(self) -> None:
        assert extract_subject_token("Re: [#TKT-42] Проблема") == 42

    def test_not_found(self) -> None:
        assert extract_subject_token("Просто тема") is None
        assert extract_subject_token(None) is None

    def test_only_first_match(self) -> None:
        assert extract_subject_token("[#TKT-1] x [#TKT-2]") == 1


class TestNormalizeEmail:
    def test_angle_brackets(self) -> None:
        assert normalize_email('"Иван" <ivan@Company.LOCAL>') == "ivan@company.local"

    def test_bare_address(self) -> None:
        assert normalize_email("ivan@host.ru") == "ivan@host.ru"

    def test_empty(self) -> None:
        assert normalize_email(None) == ""
        assert normalize_email("") == ""


class TestDisplayName:
    def test_extracted(self) -> None:
        assert extract_display_name('"Иван Петров" <ivan@h>') == "Иван Петров"

    def test_none_for_bare(self) -> None:
        assert extract_display_name("ivan@h") is None
        assert extract_display_name(None) is None


class TestSyntheticId:
    def test_deterministic(self) -> None:
        kwargs = dict(mailbox="INBOX", uid=123, date="Mon", sender="a@b", subject="s", size=10)
        assert synthetic_message_id(**kwargs) == synthetic_message_id(**kwargs)

    def test_changes_on_input(self) -> None:
        a = synthetic_message_id(
            mailbox="INBOX", uid=123, date="d", sender="a@b", subject="s", size=10
        )
        b = synthetic_message_id(
            mailbox="INBOX", uid=124, date="d", sender="a@b", subject="s", size=10
        )
        assert a != b

    def test_format(self) -> None:
        sid = synthetic_message_id(
            mailbox="INBOX", uid=1, date="d", sender="a@b", subject="s", size=1
        )
        assert sid.startswith("<synthetic:") and sid.endswith(">")


class TestOutboundMessageId:
    def test_is_outbound(self) -> None:
        assert is_outbound_message_id("<tkn-5-abc@host>") is True

    def test_not_outbound(self) -> None:
        assert is_outbound_message_id("<other@host>") is False
        assert is_outbound_message_id(None) is False

    def test_parse(self) -> None:
        import uuid

        u = uuid.uuid4()
        mid = f"<tkn-7-{u}@company.local>"
        parsed = parse_outbound_message_id(mid)
        assert parsed == (7, u)

    def test_parse_non_canonical(self) -> None:
        assert parse_outbound_message_id("<tkn-notanumber-x@h>") is None
        assert parse_outbound_message_id(None) is None


class TestDecodeMimeHeader:
    def test_koi8r_base64_subject(self) -> None:
        # Реальный кейс: тема «не работает» в KOI8-R, Base64.
        assert decode_mime_header("=?koi8-r?B?zsUgOsHCz9TBxdQ==?=") == "не :аботает"

    def test_utf8_base64_from_name(self) -> None:
        # Кодированное имя отправителя + plain адрес.
        assert decode_mime_header("=?utf-8?B?0KLQuNCy0LXRgg==?= <a@b.ru>") == (
            "Тивет <a@b.ru>"
        )

    def test_q_encoded(self) -> None:
        # Quoted-Printable variant (Windows-1251, типично для Outlook).
        assert decode_mime_header("=?windows-1251?Q?=C7=E0=EF=F0=EE=F1?=") == "Запрос"

    def test_plain_passthrough(self) -> None:
        # Без encoded-words — возвращается как есть.
        assert decode_mime_header("Simple subject") == "Simple subject"

    def test_empty_and_none(self) -> None:
        assert decode_mime_header(None) == ""
        assert decode_mime_header("") == ""

    def test_mixed_encoded_and_plain(self) -> None:
        # Токен тикета + кириллическая тема.
        out = decode_mime_header("[#TKT-5] =?utf-8?B?0J7RgtCy0LXRgg==?=")
        assert out == "[#TKT-5] Ответ"
