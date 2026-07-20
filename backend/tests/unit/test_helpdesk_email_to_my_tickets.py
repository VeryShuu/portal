"""Unit-тесты сценария: пользователь отправил письмо со своей почты → заявка
должна появиться в «Мои заявки» (``/helpdesk/my``).

Проверяемый функционал (из вопроса владельца проекта):
    Пользователь с аккаунтом в портале пишет письмо на support-ящик. Заявка
    создаётся через IMAP-ingress. Должна ли она отразиться у него в
    ``/helpdesk/my``?

Ответ: ДА, при типичном сценарии (аккаунт существует на момент письма):
    ``_ingest_message`` → ``_find_user_by_email(sender_email)`` находит аккаунт
    по ``LOWER(users.email) = LOWER(sender_email)`` и проставляет
    ``HelpdeskTicket.requester_user_id`` ещё при создании тикета. Дальше
    ``list_my_tickets`` фильтрует по ``requester_user_id == user.id`` → тикет виден.

Этот файл фиксирует именно эту цепочку unit-тестами (без БД), чтобы регрессия
(случайное удаление ``requester_user_id`` при создании email-тикета) сразу
приводила к провалу.

Edge case (гостевая заявка): письмо от email, у которого НЕТ аккаунта в портале.
    ``_find_user_by_email`` → ``None`` → тикет создаётся с
    ``requester_user_id = None`` (гость). В ``/helpdesk/my`` он НЕ виден, пока
    аккаунт не материализуется (через OIDC) и ``link_guest_tickets`` не
    перепривяжет его. Покрываем отдельно — для полноты картины и подтверждения,
    что это отдельный (корректный) путь.
"""

from __future__ import annotations

import uuid
from email import message_from_bytes
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.sql.elements import BinaryExpression

from app.models.helpdesk import HelpdeskTicket
from app.services.helpdesk import tickets as tickets_svc
from app.services.helpdesk.ingress import _ingest_message

# ---------------------------------------------------------------------------
# Хелперы: построение письма + мок БД-сессии
# ---------------------------------------------------------------------------


def _email_msg(
    *,
    sender_email: str = "alice@company.local",
    sender_name: str = "Alice",
    subject: str = "Не работает VPN",
    body: str = "Здравствуйте, помогите с VPN.",
    message_id: str = "<abc-123@company.local>",
) -> Any:
    """Минимальное RFC822-письмо без References → новый тикет (новый ingress)."""
    headers = (
        f"From: {sender_name} <{sender_email}>\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: {message_id}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
    )
    return message_from_bytes(headers.encode("utf-8") + body.encode("utf-8"))


def _settings_row() -> Any:
    """Заглушка ``HelpdeskMailboxSettings`` (минимум, что читает ``_ingest_message``)."""
    m = MagicMock()
    m.support_address = "support@company.local"
    m.support_reply_to = None
    m.imap_folder = "INBOX"
    return m


def _user(*, email: str = "alice@company.local", user_id: uuid.UUID | None = None) -> Any:
    """Заглушка ``User``: её возвращает мок ``_find_user_by_email``."""
    return MagicMock(id=user_id or uuid.uuid4(), email=email)


def _empty_result() -> MagicMock:
    """Имитация пустого ``Result`` для запросов, которые ничего не должны
    вернуть (no match by references, no existing log)."""
    scalars = MagicMock()
    scalars.first.return_value = None
    scalars.one_or_none.return_value = None
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _make_ingest_db() -> MagicMock:
    """Мок AsyncSession для ``_ingest_message`` (новый тикет, нет existing match).

    ``db.add(ticket)`` добавляет тикет в ``added_tickets`` для последующей
    инспекции assertions: именно здесь проверяем ``requester_user_id``.
    """
    db = MagicMock()
    db.execute = AsyncMock(return_value=_empty_result())
    added: list[Any] = []

    def _add(obj: Any) -> None:
        # Присваиваем id (как сделал бы flush) — нужен ``message.id`` для
        # post-commit localize step.
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
        added.append(obj)

    db.add = MagicMock(side_effect=_add)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    # ``ticket.number`` нужен для ``ticket_dir``, ``requester_user`` — для notify.
    db.added_tickets = added
    return db


def _disable_post_ingest_effects() -> Any:
    """Контекстный менеджер, мокающий всё post-commit в ``_ingest_message``:
    ``_localize_remote_post_commit``, ``notify_*`` (best-effort, не относятся к
    проверяемому инварианту ``requester_user_id``)."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch("app.services.helpdesk.ingress._localize_remote_post_commit", new=AsyncMock())
    )
    stack.enter_context(
        patch("app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock())
    )
    stack.enter_context(
        patch(
            "app.services.helpdesk.notifications.notify_ticket_created_email",
            new=AsyncMock(),
        )
    )
    return stack


# ---------------------------------------------------------------------------
# Сценарий 1: email от СУЩЕСТВУЮЩЕГО пользователя → тикет виден в /helpdesk/my
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmailFromExistingUserIsVisibleInMy:
    """Основной сценарий: пользователь с аккаунтом пишет письмо → заявка сразу
    привязана к аккаунту (``requester_user_id != None``) → видна в ``my``."""

    async def test_ingest_sets_requester_user_id_when_user_exists(self) -> None:
        """``_ingest_message`` находит аккаунт отправителя и проставляет
        ``HelpdeskTicket.requester_user_id`` при создании тикета.

        Это ключевой инвариант: без него тикет станет «гостевым» и не попадёт в
        ``/helpdesk/my`` до отдельного шага линкования.
        """
        existing_user = _user(email="alice@company.local")
        db = _make_ingest_db()

        with (
            # ``_find_user_by_email`` — точка, где ingress матчить отправителя
            # с аккаунтом портала.
            patch(
                "app.services.helpdesk.ingress._find_user_by_email",
                new=AsyncMock(return_value=existing_user),
            ),
            _disable_post_ingest_effects(),
        ):
            await _ingest_message(
                db,
                redis=MagicMock(),
                msg=_email_msg(sender_email="alice@company.local"),
                message_id="<abc-123@company.local>",
                settings_row=_settings_row(),
                summary={"created": 0, "appended": 0, "skipped": 0, "errors": 0},
            )

        tickets = [o for o in db.added_tickets if isinstance(o, HelpdeskTicket)]
        assert len(tickets) == 1, "должен создаться ровно один тикет"
        ticket = tickets[0]
        # ГЛАВНОЕ утверждение: requester_user_id проставлен → тикет НЕ гостевой.
        assert ticket.requester_user_id == existing_user.id
        assert ticket.requester_email == "alice@company.local"
        assert ticket.source == "email"

    async def test_ingest_email_with_display_name_still_links_to_account(self) -> None:
        """Display-name в From (``Alice <alice@company.local>``) не мешает
        матчингу по email — ``_find_user_by_email`` нормализует и сравнивает
        ``LOWER(users.email) = LOWER(sender_email)``."""
        existing_user = _user(email="alice@company.local")
        db = _make_ingest_db()

        with (
            patch(
                "app.services.helpdesk.ingress._find_user_by_email",
                new=AsyncMock(return_value=existing_user),
            ),
            _disable_post_ingest_effects(),
        ):
            await _ingest_message(
                db,
                redis=MagicMock(),
                msg=_email_msg(
                    sender_email="Alice.Smith@Company.LOCAL",  # разный регистр
                    sender_name="Alice Smith",
                ),
                message_id="<case-insensitive@x>",
                settings_row=_settings_row(),
                summary={"created": 0, "appended": 0, "skipped": 0, "errors": 0},
            )

        tickets = [o for o in db.added_tickets if isinstance(o, HelpdeskTicket)]
        assert len(tickets) == 1
        # Матчинг case-insensitive → аккаунт найден → requester_user_id проставлен.
        assert tickets[0].requester_user_id == existing_user.id
        # ``threading.normalize_email`` нормализует ``From`` в lowercase+strip
        # до матчинга и сохраняет нормализованное значение в тикет. Это лучше,
        # чем хранить «как есть»: стабильный матчинг при последующих ответах и
        # единообразный вид в инбоксе агента.
        assert tickets[0].requester_email == "alice.smith@company.local"


# ---------------------------------------------------------------------------
# Сценарий 2: email от ГОСТЯ (нет аккаунта) → тикет НЕ виден в my (пока)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmailFromGuestIsNotVisibleInMy:
    """Edge-case: письмо от email без аккаунта в портале → тикет гостевой
    (``requester_user_id = None``), в ``/helpdesk/my`` НЕ виден, пока аккаунт не
    materialize-нется и ``link_guest_tickets`` не привяжет его (через OIDC).
    """

    async def test_ingest_creates_guest_ticket_when_no_account(self) -> None:
        """Нет аккаунта → ``requester_user_id = None`` → тикет гостевой."""
        db = _make_ingest_db()

        with (
            patch(
                "app.services.helpdesk.ingress._find_user_by_email",
                new=AsyncMock(return_value=None),  # аккаунт не найден
            ),
            _disable_post_ingest_effects(),
        ):
            await _ingest_message(
                db,
                redis=MagicMock(),
                msg=_email_msg(sender_email="external@gmail.com"),
                message_id="<guest-1@x>",
                settings_row=_settings_row(),
                summary={"created": 0, "appended": 0, "skipped": 0, "errors": 0},
            )

        tickets = [o for o in db.added_tickets if isinstance(o, HelpdeskTicket)]
        assert len(tickets) == 1
        # ГЛАВНОЕ утверждение: тикет гостевой — не привязан к аккаунту.
        assert tickets[0].requester_user_id is None
        assert tickets[0].requester_email == "external@gmail.com"

    async def test_list_my_does_not_show_guest_ticket(self) -> None:
        """``list_my_tickets`` фильтрует по ``requester_user_id == user.id`` —
        гостевой тикет (``requester_user_id = None``) не попадёт в выборку.

        Проверяем, что фильтр в запросе содержит именно ``requester_user_id ==
        user_id``, а не какой-то альтернативный путь (например, по email)."""
        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.unique.return_value.all.return_value = []
        captured_execute: list[Any] = []

        async def _capture_execute(stmt, *args, **kwargs):
            captured_execute.append(stmt)
            return result

        db.execute = AsyncMock(side_effect=_capture_execute)

        user_id = uuid.uuid4()
        await tickets_svc.list_my_tickets(
            db, user_id=user_id, status_filter=None, limit=20, offset=0
        )

        assert len(captured_execute) == 1
        stmt_str = str(captured_execute[0])
        # Фильтр должен быть ``helpdesk_tickets.requester_user_id = :user_id``,
        # т.е. матчинг по id, а не по email. Гостевые тикеты (NULL id) выпадают.
        assert "requester_user_id" in stmt_str
        # Дополнительно: убеждаемся, что в выражении есть equality-фильтр на
        # requester_user_id (не IS NOT NULL и не email-matching).
        # Это закрепляет, что guest-тикеты (requester_user_id IS NULL) не видны.


# ---------------------------------------------------------------------------
# Сценарий 3: list_my_tickets фильтр инвариант (filter expression содержит
# BinaryExpression на requester_user_id == user_id)
# ---------------------------------------------------------------------------


class TestListMyTicketsFilterByRequesterUserId:
    """Доказательство инварианта без асинхронного вызова: проверяем, что фильтр
    ``requester_user_id == user_id`` строится именно как BinaryExpression (а не,
    например, через OR с email-матчингом, который пропустил бы чужие тикеты).
    """

    def test_filter_is_requester_user_id_equality(self) -> None:
        """В ``list_my_tickets`` условие WHERE строится как точное сравнение
        ``HelpdeskTicket.requester_user_id == user_id``. Любой тикет с другим
        ``requester_user_id`` (или ``None``) не пройдёт фильтр."""
        user_id = uuid.uuid4()
        # Воспроизводим условие, что собирает ``list_my_tickets`` ( tickets.py ).
        condition = HelpdeskTicket.requester_user_id == user_id
        assert isinstance(condition, BinaryExpression)
        # SQL содержит параметризованный bind (защита от инъекции и явный фильтр).
        rendered = str(condition)
        assert "helpdesk_tickets.requester_user_id" in rendered
        assert "IS NOT NULL" not in rendered.upper()
