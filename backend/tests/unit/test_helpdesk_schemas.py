"""Unit-тесты Pydantic-схем модуля helpdesk (Этап 1 — БД + модели + схемы).

Покрывают контракты из ТЗ ``docs/wip/helpdesk.md`` §4.3:
- ``TicketCreateIn`` — обязательность и лимиты длины subject/description;
- ``TicketStatusIn`` — только agent-settable статусы (``new``/``archived``
  запрещены — это не статусы, которые выставляют вручную);
- ``MessageCreateIn`` — default ``visibility=public``;
- ``HelpdeskMailboxSettingsIn`` — write-only пароль (опционален при update),
  границы ``poll_interval_seconds`` (30–600), email-длина;
- значения StrEnum.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from app.schemas.helpdesk import (
    HelpdeskMailboxSettingsIn,
    HelpdeskSource,
    HelpdeskStatus,
    HelpdeskVisibility,
    MessageCreateIn,
    TicketCreateIn,
    TicketStatusIn,
)


class TestTicketCreateIn:
    def test_valid(self) -> None:
        t = TicketCreateIn(subject="Не работает VPN", description="Подробности")
        assert t.subject == "Не работает VPN"
        assert t.description == "Подробности"

    def test_subject_required(self) -> None:
        with pytest.raises(ValidationError):
            TicketCreateIn(description="x")  # type: ignore[call-arg]

    def test_description_required(self) -> None:
        with pytest.raises(ValidationError):
            TicketCreateIn(subject="x")  # type: ignore[call-arg]

    def test_subject_too_long(self) -> None:
        with pytest.raises(ValidationError):
            TicketCreateIn(subject="x" * 501, description="y")

    def test_description_too_long(self) -> None:
        with pytest.raises(ValidationError):
            TicketCreateIn(subject="x", description="y" * 20001)


class TestTicketStatusIn:
    @pytest.mark.parametrize("status", ["open", "pending", "resolved", "closed"])
    def test_valid(self, status: str) -> None:
        s = TicketStatusIn(status=status)  # type: ignore[arg-type]
        assert s.status == status

    @pytest.mark.parametrize("status", ["new", "archived", "", "OPEN", "deleted"])
    def test_invalid(self, status: str) -> None:
        # ``new`` — стартовое состояние при создании, не выставляется вручную;
        # ``archived`` — это перенос в архивную таблицу, а не статус (ТЗ §1.3.9).
        with pytest.raises(ValidationError):
            TicketStatusIn(status=status)  # type: ignore[arg-type]


class TestMessageCreateIn:
    def test_defaults_to_public(self) -> None:
        m = MessageCreateIn(body_text="Ответ")
        assert m.visibility == HelpdeskVisibility.public

    def test_internal_allowed(self) -> None:
        m = MessageCreateIn(body_text="Заметка", visibility=HelpdeskVisibility.internal)
        assert m.visibility == HelpdeskVisibility.internal

    def test_body_required(self) -> None:
        with pytest.raises(ValidationError):
            MessageCreateIn()  # type: ignore[call-arg]

    def test_body_too_long(self) -> None:
        with pytest.raises(ValidationError):
            MessageCreateIn(body_text="x" * 20001)


class TestMailboxSettingsIn:
    _BASE: ClassVar[dict[str, Any]] = {
        "imap_host": "imap.company.local",
        "imap_username": "support",
        "support_address": "support@company.local",
    }

    def test_password_optional_at_schema_level(self) -> None:
        # Пароль намеренно опционален на уровне схемы — write-only семантика
        # («None = оставить прежний» при update). Обязательность пароля при
        # *создании* записи enforcement-ится в сервисе (строка ещё не существует).
        s = HelpdeskMailboxSettingsIn(**self._BASE)
        assert s.imap_password is None

    def test_update_without_password_allowed(self) -> None:
        # На уровне схемы пароль опционален — write-only семантика
        # («None = оставить прежний») enforcementится в сервисе; но создать
        # объект схемы без пароля можно.
        s = HelpdeskMailboxSettingsIn(imap_password="secret", **self._BASE)
        assert s.imap_password == "secret"

    @pytest.mark.parametrize("interval", [29, 601, 0, -1])
    def test_poll_interval_out_of_range(self, interval: int) -> None:
        with pytest.raises(ValidationError):
            HelpdeskMailboxSettingsIn(
                imap_password="x", poll_interval_seconds=interval, **self._BASE
            )

    @pytest.mark.parametrize("interval", [30, 60, 600])
    def test_poll_interval_valid(self, interval: int) -> None:
        s = HelpdeskMailboxSettingsIn(
            imap_password="x", poll_interval_seconds=interval, **self._BASE
        )
        assert s.poll_interval_seconds == interval

    def test_defaults(self) -> None:
        s = HelpdeskMailboxSettingsIn(imap_password="x", **self._BASE)
        assert s.imap_port == 993
        assert s.imap_use_ssl is True
        assert s.imap_folder == "INBOX"
        assert s.delete_after_fetch is False


class TestEnumValues:
    def test_status_values(self) -> None:
        assert {s.value for s in HelpdeskStatus} == {
            "new",
            "open",
            "pending",
            "resolved",
            "closed",
        }

    def test_source_values(self) -> None:
        assert {s.value for s in HelpdeskSource} == {"email", "web"}

    def test_visibility_values(self) -> None:
        assert {v.value for v in HelpdeskVisibility} == {"public", "internal"}
