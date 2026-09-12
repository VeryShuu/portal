"""Unit-тесты ``_match_ticket`` — защита от email-инъекции в чужой тикет (#5).

CRITICAL-баг: матчинг по ``[#TKT-N]`` в теме и ``+TKT-N`` в адресе получателя
(fallback'и) не проверял, что отправитель = заявитель тикета. ``number``
последователен (IDENTITY) и угадываем → сторонним письмом с ``[#TKT-123]``
можно было подмешать сообщение в чужой тикет.

Фикс: для subject/recipient-token fallback'ов сверяем ``sender_email`` с
``ticket.requester_email`` (case-insensitive). ``references``-матч (секретный
``Message-ID`` исходящего письма) — без сверки (не угадывается).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.helpdesk.ingress import _match_ticket


def _ticket(*, number: int, requester_email: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=number,
        requester_email=requester_email,
    )


def _result(rows: list) -> MagicMock:
    scalars = MagicMock()
    scalars.first.return_value = rows[0] if rows else None
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _make_db(*results) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


@pytest.mark.asyncio
class TestMatchTicketSenderCheck:
    async def test_subject_token_correct_sender_matches(self) -> None:
        """``[#TKT-123]`` в теме + отправитель = заявитель → матч."""
        ticket = _ticket(number=123, requester_email="client@example.com")
        db = _make_db(_result([ticket]))

        result = await _match_ticket(
            db,
            references=[],
            subject_token=123,
            recipient_token=None,
            sender_email="client@example.com",
        )

        assert result is ticket

    async def test_subject_token_wrong_sender_creates_new_ticket(self) -> None:
        """``[#TKT-123]`` в теме, но отправитель ≠ заявитель → None (новый тикет).

        Это и есть фикcимый SSRF-инъекционный вектор: раньше чужое письмо с
        угаданным номером подмешивалось в чужой тикет."""
        ticket = _ticket(number=123, requester_email="client@example.com")
        db = _make_db(_result([ticket]))

        result = await _match_ticket(
            db,
            references=[],
            subject_token=123,
            recipient_token=None,
            sender_email="attacker@evil.com",
        )

        assert result is None

    async def test_sender_check_case_insensitive(self) -> None:
        """Сверка email case-insensitive (``Client@Example.com`` == заявитель)."""
        ticket = _ticket(number=123, requester_email="client@example.com")
        db = _make_db(_result([ticket]))

        result = await _match_ticket(
            db,
            references=[],
            subject_token=123,
            recipient_token=None,
            sender_email="CLIENT@EXAMPLE.COM",
        )

        assert result is ticket

    async def test_recipient_token_wrong_sender_creates_new_ticket(self) -> None:
        """``+TKT-123`` в адресе получателя, отправитель ≠ заявитель → None."""
        ticket = _ticket(number=123, requester_email="client@example.com")
        db = _make_db(_result([ticket]))

        result = await _match_ticket(
            db,
            references=[],
            subject_token=None,
            recipient_token=123,
            sender_email="attacker@evil.com",
        )

        assert result is None

    async def test_references_match_ignores_sender(self) -> None:
        """``references``-матч (секретный Message-ID) — без сверки отправителя.

        Message-ID исходящего письма не угадывается → если письмо ссылается на
        него через In-Reply-To/References, это легитимный ответ в тред,
        независимо от отправителя (forwarding/CC-сценарии)."""
        ticket = _ticket(number=123, requester_email="client@example.com")
        db = _make_db(_result([ticket]))

        result = await _match_ticket(
            db,
            references=["<tkn-123-abc@support.example.com>"],
            subject_token=None,
            recipient_token=None,
            sender_email="completely@different.com",
        )

        assert result is ticket

    async def test_no_token_no_references_returns_none(self) -> None:
        """Ни references, ни токенов → None (новый тикет)."""
        db = _make_db()

        result = await _match_ticket(
            db,
            references=[],
            subject_token=None,
            recipient_token=None,
            sender_email="someone@example.com",
        )

        assert result is None

    async def test_token_but_no_live_ticket_returns_none(self) -> None:
        """Токен есть, но живого тикета с таким номером нет (архивный) → None.
        Caller создаст новый тикет со ссылкой references_archived_ticket_number."""
        db = _make_db(_result([]))

        result = await _match_ticket(
            db,
            references=[],
            subject_token=999,
            recipient_token=None,
            sender_email="someone@example.com",
        )

        assert result is None
