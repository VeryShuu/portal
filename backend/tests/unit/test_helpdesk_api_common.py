"""Unit-тесты чистых функций helpdesk API (mappers + ACL-фильтр).

Не требуют БД: оперируют in-memory объектами моделей, построенными через
полифабрику-подобные хелперы. Главный проверяемый инвариант Этапа 2 —
``internal``-сообщения никогда не попадают в публичное представление тикета
(ТЗ §3.2, §4.5), даже если оказались в загруженной коллекции.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api.helpdesk._common import (
    build_requester_profile,
    message_to_out,
    ticket_to_out,
)
from app.models.helpdesk import HelpdeskAttachment, HelpdeskMessage, HelpdeskTicket
from app.models.user import User


def _msg(
    *,
    direction: str = "inbound",
    visibility: str = "public",
    body_text: str = "текст",
    attachments: list[HelpdeskAttachment] | None = None,
) -> HelpdeskMessage:
    m = HelpdeskMessage(
        id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        author_email="user@portal.local",
        author_name="User",
        direction=direction,
        visibility=visibility,
        body_text=body_text,
        source="web",
        created_at=datetime.now(UTC),
    )
    # relationship назначаем post-hoc (модель в unit-тесте без БД).
    m.attachments = attachments or []  # type: ignore[assignment]
    return m


def _ticket(messages: list[HelpdeskMessage]) -> HelpdeskTicket:
    return HelpdeskTicket(
        id=uuid.uuid4(),
        subject="Тема",
        description="Описание",
        status="new",
        source="web",
        requester_email="user@portal.local",
        requester_name="User",
        number=10,
        messages=messages,  # type: ignore[call-arg]
        created_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )


class TestPublicAclFilter:
    def test_internal_messages_excluded_for_requester(self) -> None:
        ticket = _ticket(
            [
                _msg(visibility="public", body_text="видно"),
                _msg(visibility="internal", body_text="секрет"),
                _msg(visibility="public", body_text="тоже видно"),
            ]
        )
        out = ticket_to_out(ticket, requester_view=True)
        bodies = [m.body_text for m in out.messages]
        assert bodies == ["видно", "тоже видно"]

    def test_internal_messages_kept_in_agent_view(self) -> None:
        ticket = _ticket(
            [
                _msg(visibility="public"),
                _msg(visibility="internal", body_text="секрет"),
            ]
        )
        out = ticket_to_out(ticket, requester_view=False)
        assert len(out.messages) == 2

    def test_empty_messages(self) -> None:
        out = ticket_to_out(_ticket([]), requester_view=True)
        assert out.messages == []

    def test_internal_never_leaks_even_with_single_message(self) -> None:
        ticket = _ticket([_msg(visibility="internal")])
        out = ticket_to_out(ticket, requester_view=True)
        assert out.messages == []


class TestMessageMapper:
    def test_basic_mapping(self) -> None:
        m = _msg(direction="outbound", visibility="internal", body_text="н")
        out = message_to_out(m)
        assert out.direction.value == "outbound"
        assert out.visibility.value == "internal"
        assert out.body_text == "н"

    def test_status_enum_coercion(self) -> None:
        # Статус хранится строкой; mapper переводит в StrEnum.
        ticket = _ticket([])
        ticket.status = "resolved"
        out = ticket_to_out(ticket)
        assert out.status.value == "resolved"


class TestAttachmentsMapping:
    """Вложения сообщения должны попадать в MessageOut.attachments, чтобы
    фронтенд мог их отрендерить после перезагрузки страницы (фикс «файл
    пропадает после обновления» — без этих данных в ответе UI нечего показать)."""

    def _att(self, name: str = "doc.pdf") -> HelpdeskAttachment:
        return HelpdeskAttachment(
            id=uuid.uuid4(),
            ticket_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            filename=f"{uuid.uuid4().hex}_doc.pdf",
            original_name=name,
            content_type="application/pdf",
            size_bytes=1024,
            created_at=datetime.now(UTC),
        )

    def test_message_with_attachments(self) -> None:
        m = _msg(attachments=[self._att("a.pdf"), self._att("b.pdf")])
        out = message_to_out(m)
        assert len(out.attachments) == 2
        assert out.attachments[0].original_name == "a.pdf"
        assert out.attachments[1].original_name == "b.pdf"

    def test_message_without_attachments(self) -> None:
        out = message_to_out(_msg())
        assert out.attachments == []

    def test_attachments_visible_in_ticket_out(self) -> None:
        """Сквозной путь: attachments сообщения попадают в TicketOut (requester)."""
        att = self._att("report.xlsx")
        ticket = _ticket([_msg(attachments=[att])])
        out = ticket_to_out(ticket, requester_view=True)
        assert out.messages[0].attachments[0].original_name == "report.xlsx"


def _user(
    *,
    email: str = "user@portal.local",
    full_name: str = "User",
    department: str | None = "IT",
    position: str | None = "Engineer",
    phone: str | None = "123",
    attributes: dict | None = None,
) -> User:
    """In-memory User (unit-тест без БД)."""
    return User(
        email=email,
        full_name=full_name,
        department=department,
        position=position,
        phone=phone,
        role="reader",
        auth_source="local",
        presence_status="office",
        lang="ru",
        attributes=attributes if attributes is not None else {},
    )


class TestRequesterProfile:
    """Сборка краткого профиля заявителя из модели User для карточки тикета.

    city/mobile берутся из JSONB attributes, internal_phone — из нативной
    колонки phone. Гостевая заявка (User is None) → профиль не строится."""

    def test_none_user_returns_none(self) -> None:
        assert build_requester_profile(None) is None

    def test_full_profile_from_attributes(self) -> None:
        user = _user(
            attributes={"city": "Москва", "mobile": "+7 900 123-45-67"},
        )
        profile = build_requester_profile(user)
        assert profile is not None
        assert profile.email == "user@portal.local"
        assert profile.full_name == "User"
        assert profile.department == "IT"
        assert profile.position == "Engineer"
        assert profile.city == "Москва"
        assert profile.mobile_phone == "+7 900 123-45-67"
        assert profile.internal_phone == "123"

    def test_missing_attributes_yield_none(self) -> None:
        user = _user(attributes={})
        profile = build_requester_profile(user)
        assert profile is not None
        assert profile.city is None
        assert profile.mobile_phone is None
        assert profile.internal_phone == "123"  # phone — нативная колонка

    def test_non_string_attributes_ignored(self) -> None:
        # Числовые/пустые значения из attributes не должны попасть в профиль.
        user = _user(attributes={"city": 42, "mobile": ""})
        profile = build_requester_profile(user)
        assert profile is not None
        assert profile.city is None
        assert profile.mobile_phone is None

    def test_empty_phone_yields_none(self) -> None:
        user = _user(phone="")
        profile = build_requester_profile(user)
        assert profile is not None
        assert profile.internal_phone is None


class TestTicketOutRequesterProfile:
    """Профиль заявителя должен попадать в TicketOut/TicketAgentOut при передаче."""

    def test_ticket_to_out_without_profile(self) -> None:
        out = ticket_to_out(_ticket([]), requester_view=True)
        assert out.requester_profile is None

    def test_ticket_to_out_with_profile(self) -> None:
        profile = build_requester_profile(_user(attributes={"city": "Москва"}))
        assert profile is not None
        out = ticket_to_out(_ticket([]), requester_view=True, requester_profile=profile)
        assert out.requester_profile is not None
        assert out.requester_profile.city == "Москва"
