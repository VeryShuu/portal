"""Unit-тесты anti-loop detection в helpdesk ingress (Этап 5, ТЗ §5.3).

Чистые функции без БД/сети: ``is_auto_reply`` (по ``Auto-Submitted`` /
``Precedence`` / ``X-Auto-Response-Suppress``) и ``is_from_self`` (петля:
``From`` == ``support_address``).
"""

from __future__ import annotations

from email.message import Message

from app.services.helpdesk.ingress import is_auto_reply, is_from_self


def _msg(headers: dict[str, str]) -> Message:
    m = Message()
    for k, v in headers.items():
        m[k] = v
    return m


class TestIsAutoReply:
    def test_auto_submitted_auto_replied(self) -> None:
        assert is_auto_reply(_msg({"Auto-Submitted": "auto-replied"})) is True

    def test_auto_submitted_auto_generated(self) -> None:
        assert is_auto_reply(_msg({"Auto-Submitted": "auto-generated"})) is True

    def test_auto_submitted_auto_notified(self) -> None:
        assert is_auto_reply(_msg({"Auto-Submitted": "auto-notified"})) is True

    def test_precedence_bulk(self) -> None:
        assert is_auto_reply(_msg({"Precedence": "bulk"})) is True

    def test_precedence_list(self) -> None:
        assert is_auto_reply(_msg({"Precedence": "list"})) is True

    def test_precedence_junk(self) -> None:
        assert is_auto_reply(_msg({"Precedence": "junk"})) is True

    def test_x_auto_response_suppress(self) -> None:
        assert is_auto_reply(_msg({"X-Auto-Response-Suppress": "All"})) is True

    def test_normal_message_not_auto(self) -> None:
        assert is_auto_reply(_msg({})) is False

    def test_subject_only_not_auto(self) -> None:
        assert is_auto_reply(_msg({"Subject": "hi"})) is False


class TestIsFromSelf:
    def test_self_address_is_loop(self) -> None:
        msg = _msg({"From": "Support <support@company.local>"})
        assert is_from_self(msg, "support@company.local") is True

    def test_other_sender_not_loop(self) -> None:
        msg = _msg({"From": "user@external.com"})
        assert is_from_self(msg, "support@company.local") is False

    def test_case_insensitive(self) -> None:
        msg = _msg({"From": "SUPPORT@Company.Local"})
        assert is_from_self(msg, "support@company.local") is True

    def test_empty_from_not_loop(self) -> None:
        assert is_from_self(_msg({}), "support@company.local") is False
