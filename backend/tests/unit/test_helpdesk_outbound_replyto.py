"""Unit-тесты выбора ``Reply-To`` и sanitize ``references`` в outbound-продюсерах.

Покрывает две правки production-readiness аудита:

* **H-4** — ``support_reply_to`` (mailbox-настройка) теперь реально используется
  продюсерами через ``reply_to_address``: явное значение побеждает, иначе
  ``support_address``. Раньше поле сохранялось в БД, но игнорировалось во всех
  продюсерах — введённое админом значение терялось.
* **C-3** — ``references``/``in_reply_to`` из БД прогоняются через
  ``_sanitize_header_field`` в продюсере (defense-in-depth: worker стрипает
  повторно). ``references`` берутся из ``email_message_id`` входящих писем —
  attacker-controlled, без стрипа CRLF инжектят заголовок в исходящем письме.

``enqueue_outbox_email`` мокается (паттерн ``test_helpdesk_outbound_enqueue``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.models.user import User
from app.services.helpdesk.outbound import (
    _sanitize_references,
    enqueue_assigned_email,
    enqueue_created_email,
    enqueue_reply_outbound,
    reply_to_address,
)


class _UserFactory(SQLAlchemyFactory[User]):
    """In-memory ``User`` через polyfactory — типизированный объект вместо
    ``SimpleNamespace`` для ``assignee``/``actor`` (mypy строгий на ``tests/``)."""

    __model__ = User
    __set_relationships__ = False


def _mailbox(*, support_reply_to: str | None = None) -> Any:
    """Mailbox-settings заглушка. По умолчанию явный Reply-To не задан — должна
    браться база поддержки (``support_address``)."""
    return SimpleNamespace(
        support_address="portal@company.local",
        support_reply_to=support_reply_to,
    )


class TestReplyToAddress:
    """``reply_to_address`` — единственная точка выбора Reply-To."""

    def test_falls_back_to_support_address_when_no_explicit(self) -> None:
        """H-4: при ``support_reply_to=None`` (или пустой) берётся
        ``support_address`` — базовое поведение до правки."""
        mb = _mailbox(support_reply_to=None)
        assert reply_to_address(mb) == "portal@company.local"

    def test_falls_back_on_empty_string(self) -> None:
        mb = _mailbox(support_reply_to="   ")
        assert reply_to_address(mb) == "portal@company.local"

    def test_uses_explicit_reply_to_when_set(self) -> None:
        """H-4: явный ``support_reply_to`` (задан админом в mailbox-настройках)
        побеждает ``support_address``."""
        mb = _mailbox(support_reply_to="noreply@company.local")
        assert reply_to_address(mb) == "noreply@company.local"

    def test_strips_whitespace_around_explicit(self) -> None:
        mb = _mailbox(support_reply_to="  noreply@company.local  ")
        assert reply_to_address(mb) == "noreply@company.local"


class TestSanitizeReferences:
    """``_sanitize_references`` — defense-in-depth CRLF-strip для references."""

    def test_strips_crlf_from_each_reference(self) -> None:
        """C-3: ``email_message_id`` входящего письма attacker-controlled.
        CRLF в нём инжектит заголовок в исходящем письме — стрипаем в продюсере."""
        refs = [
            "<legit@company.local>",
            "<evil@company.local>\r\nBcc: leak@evil.test",
            "<another\r\n>\nX-Inject: yes",
        ]
        cleaned = _sanitize_references(refs)
        assert len(cleaned) == 3
        for r in cleaned:
            assert "\r" not in r, f"CRLF не стрипнут: {r!r}"
            assert "\n" not in r, f"CRLF не стрипнут: {r!r}"

    def test_drops_empty_entries(self) -> None:
        """Пустые/``None``-значения фильтруются (``collect_ticket_references``
        уже фильтрует, но защита от будущего изменения источника)."""
        assert _sanitize_references(["<a@x>", "", None, "<b@x>"]) == ["<a@x>", "<b@x>"]  # type: ignore[list-item]

    def test_preserves_legitimate_references(self) -> None:
        refs = ["<tkn-1-aaa@company.local>", "<tkn-1-bbb@company.local>"]
        assert _sanitize_references(refs) == refs


def _current_message() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        body_text="Ответ агента.",
        body_html="<p>Ответ агента.</p>",
        direction="outbound",
        author_name="Агент",
        author_email="portal@company.local",
        created_at=datetime(2026, 7, 1, 12, 0),
        email_message_id="<tkn-5-curr@company.local>",
        author_user_id=uuid.uuid4(),
    )


def _ticket() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        number=5,
        subject="Тема заявки",
        requester_email="client@company.local",
        requester_user_id=uuid.uuid4(),
        messages=[],
        assignee_user_id=None,
    )


def _make_db_with_refs(refs: list[str], *, has_attachments_query: bool = False) -> MagicMock:
    """``enqueue_reply_outbound`` делает два ``db.execute`` (references + attachments),
    ``enqueue_assigned_email``/``enqueue_created_email`` — один (references).

    * ``has_attachments_query=False`` (default) — один execute, возвращает ``refs``.
      Годится для assigned/created-email продюсеров.
    * ``has_attachments_query=True`` — два execute: первый (references) отдаёт
      ``refs``, второй (attachments meta) — ``[]`` (без вложений в тесте).
    """
    refs_result = MagicMock()
    refs_result.scalars.return_value.all.return_value = refs
    db = MagicMock()
    if has_attachments_query:
        atts_result = MagicMock()
        atts_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[refs_result, atts_result])
    else:
        db.execute = AsyncMock(return_value=refs_result)
    return db


@pytest.mark.asyncio
class TestProducersUseExplicitReplyTo:
    """Все три продюсера (reply/assigned/created) ставят ``payload.reply_to`` из
    ``reply_to_address``, а не хардкодят ``support_address`` (H-4)."""

    async def test_reply_outbound_uses_explicit_reply_to(self) -> None:
        mb = _mailbox(support_reply_to="noreply@company.local")
        db = _make_db_with_refs([], has_attachments_query=True)

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=_ticket(), message=_current_message(), mailbox=mb
            )

        assert enqueue.await_args is not None
        assert enqueue.await_args.kwargs["payload"]["reply_to"] == "noreply@company.local"

    async def test_reply_outbound_falls_back_to_support_address(self) -> None:
        """Без явного Reply-To — берётся ``support_address`` (бывшее поведение)."""
        mb = _mailbox(support_reply_to=None)
        db = _make_db_with_refs([], has_attachments_query=True)

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=_ticket(), message=_current_message(), mailbox=mb
            )

        assert enqueue.await_args is not None
        assert enqueue.await_args.kwargs["payload"]["reply_to"] == "portal@company.local"

    async def test_assigned_email_uses_explicit_reply_to(self) -> None:
        mb = _mailbox(support_reply_to="noreply@company.local")
        db = _make_db_with_refs([])
        assignee = _UserFactory.build(id=uuid.uuid4(), full_name="Агент", email="a@x.test")
        actor = _UserFactory.build(id=uuid.uuid4(), full_name="Админ", email="adm@x.test")

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_assigned_email(
                db, ticket=_ticket(), assignee=assignee, actor=actor, mailbox=mb
            )

        assert enqueue.await_args is not None
        assert enqueue.await_args.kwargs["payload"]["reply_to"] == "noreply@company.local"

    async def test_created_email_uses_explicit_reply_to(self) -> None:
        mb = _mailbox(support_reply_to="noreply@company.local")
        db = _make_db_with_refs([])

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_created_email(db, ticket=_ticket(), mailbox=mb)

        assert enqueue.await_args is not None
        assert enqueue.await_args.kwargs["payload"]["reply_to"] == "noreply@company.local"


@pytest.mark.asyncio
class TestProducersSanitizeReferences:
    """C-3: ``references``/``in_reply_to`` в payload санизируются в продюсере."""

    async def test_reply_outbound_strips_crlf_from_references(self) -> None:
        """References с CRLF (из подделанного ``In-Reply-To`` входящего письма)
        не должны попадать в payload — header-injection в исходящем письме."""
        mb = _mailbox()
        evil_refs = [
            "<legit@company.local>",
            "<evil@company.local>\r\nBcc: leak@evil.test",
        ]
        db = _make_db_with_refs(evil_refs, has_attachments_query=True)

        with patch(
            "app.services.helpdesk.outbound.enqueue_outbox_email", new=AsyncMock()
        ) as enqueue:
            await enqueue_reply_outbound(
                db, ticket=_ticket(), message=_current_message(), mailbox=mb
            )

        assert enqueue.await_args is not None
        payload = enqueue.await_args.kwargs["payload"]
        # references — без CRLF.
        for r in payload["references"]:
            assert "\r" not in r and "\n" not in r, f"CRLF в reference: {r!r}"
        # in_reply_to (последний reference) — тоже без CRLF.
        assert "\r" not in payload["in_reply_to"]
        assert "\n" not in payload["in_reply_to"]
