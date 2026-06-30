"""Unit-тесты чистых функций helpdesk API (mappers + ACL-фильтр).

Не требуют БД: оперируют in-memory объектами моделей, построенными через
полифабрику-подобные хелперы. Главный проверяемый инвариант Этапа 2 —
``internal``-сообщения никогда не попадают в публичное представление тикета
(ТЗ §3.2, §4.5), даже если оказались в загруженной коллекции.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api.helpdesk._common import message_to_out, ticket_to_out
from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket


def _msg(
    *,
    direction: str = "inbound",
    visibility: str = "public",
    body_text: str = "текст",
) -> HelpdeskMessage:
    return HelpdeskMessage(
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
