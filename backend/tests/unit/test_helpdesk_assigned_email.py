"""Unit-тесты построителя email-уведомления о назначении ответственного.

Письмо инициатору (ТЗ §6) должно: содержать ФИО ответственного, номер и тему
заявки, тикет-токен ``[#TKT-{number}]`` в теме (для Subject-matching входящих
ответов), HTML-экранирование пользовательских данных (тема/ФИО).

Чистые функции ``build_assigned_email_*`` не требуют БД.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.helpdesk import HelpdeskTicket
from app.models.user import User
from app.services.helpdesk.notifications import (
    build_assigned_email_bodies,
    build_assigned_email_subject,
)


def _ticket(*, number: int = 42, subject: str = "Не работает VPN") -> HelpdeskTicket:
    return HelpdeskTicket(
        id=uuid.uuid4(),
        subject=subject,
        description="описание",
        status="open",
        source="web",
        requester_email="user@portal.local",
        requester_name="User",
        number=number,
        created_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )


def _user(*, full_name: str = "Иван Иванов") -> User:
    return User(
        id=uuid.uuid4(),
        email="agent@portal.local",
        full_name=full_name,
        role="editor",
    )


class TestAssignedEmailSubject:
    def test_subject_has_ticket_token(self) -> None:
        ticket = _ticket(number=42)
        subject = build_assigned_email_subject(ticket)
        assert subject.startswith("[#TKT-42] ")

    def test_subject_independent_of_ticket_subject(self) -> None:
        """Тема письма о назначении — фиксированная («принята в работу»), не
        дублирует тему заявки (тема заявки уже была в исходном письме-создании
        и в Subject-токене достаточно для matching)."""
        ticket = _ticket(subject="Что-то случилось")
        subject = build_assigned_email_subject(ticket)
        assert "Что-то случилось" not in subject
        assert "принята в работу" in subject.lower()


class TestAssignedEmailBodies:
    def test_plain_contains_assignee_full_name(self) -> None:
        ticket = _ticket(number=42, subject="VPN")
        assignee = _user(full_name="Мария Петрова")
        _html, plain = build_assigned_email_bodies(ticket, assignee)
        assert "Мария Петрова" in plain

    def test_plain_has_ticket_number_from_template(self) -> None:
        """Номер и тема приходят из шапки шаблона render_system_email."""
        ticket = _ticket(number=42, subject="VPN тема")
        assignee = _user()
        _html, plain = build_assigned_email_bodies(ticket, assignee)
        assert "TKT-42" in plain
        assert "VPN тема" in plain

    def test_plain_has_reply_hint_with_token(self) -> None:
        ticket = _ticket(number=42)
        assignee = _user()
        _html, plain = build_assigned_email_bodies(ticket, assignee)
        # Ответ заявителя должен сохранить токен в теме.
        assert "[#TKT-42]" in plain

    def test_html_escapes_subject_and_name(self) -> None:
        """XSS-защита: тема/ФИО с HTML-спецсимволами экранируются."""
        ticket = _ticket(number=1, subject="<script>alert(1)</script>")
        assignee = _user(full_name="Иван <b>& Co</b>")
        html_body, _plain = build_assigned_email_bodies(ticket, assignee)
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body
        assert "&lt;b&gt;" in html_body

    def test_html_contains_assignee_and_number(self) -> None:
        ticket = _ticket(number=42, subject="VPN")
        assignee = _user(full_name="Пётр Сидоров")
        html_body, _plain = build_assigned_email_bodies(ticket, assignee)
        assert "TKT-42" in html_body
        assert "Пётр Сидоров" in html_body
        assert "[#TKT-42]" in html_body

    def test_plain_and_html_returned_as_tuple(self) -> None:
        ticket = _ticket()
        assignee = _user()
        result = build_assigned_email_bodies(ticket, assignee)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)
