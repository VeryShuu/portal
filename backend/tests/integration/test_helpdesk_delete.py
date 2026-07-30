"""Integration tests for admin-only full ticket deletion (helpdesk).

Покрывает:
* сервисный ``delete_ticket`` — hard-delete + CASCADE (сообщения/вложения/
  marker-reads исчезают) + возврат человекочитаемого ``number``;
* роутерный ``DELETE /tickets/{id}`` (вызов endpoint-функции напрямую, как
  ``test_helpdesk_agents``) — admin-only ACL: editor/reader/helpdesk-agent-без-
  admin-роли получают 403 через ``require_admin`` (deps), admin получает 204,
  несуществующий id → 404.

Hard-delete сознательно расширяет архивный паттерн helpdesk (где закрытые
тикеты уже удаляются из живой таблицы): спам-очистка / GDPR-удаление.
Архив (``helpdesk_tickets_archive``) и уведомления не затрагиваются — см.
``services/helpdesk/tickets.py::delete_ticket``.

Авто-skip'ается без ``INTEGRATION_DB=true`` (нет реальной PostgreSQL — CASCADE
проверяется только на живой БД).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.models.helpdesk import HelpdeskAttachment, HelpdeskMessage, HelpdeskTicket
from app.schemas.helpdesk import TicketCreateIn
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    """Мок Redis для ``push_audit_event`` (rpush → Redis-очередь аудита)."""
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    """Заявка от reader'а с первым сообщением (инвариант — см. ``create_ticket``)."""
    return await tickets_service.create_ticket(
        real_db_session,
        user=real_user,
        payload=TicketCreateIn(subject="Спам-заявка", description="подлежит удалению"),
        files=[],
    )


# ---------------------------------------------------------------------------
# Сервисный слой: delete_ticket + CASCADE
# ---------------------------------------------------------------------------


class TestDeleteTicketService:
    async def test_returns_human_readable_number(self, real_db_session, ticket):
        number = await tickets_service.delete_ticket(real_db_session, ticket=ticket)
        assert isinstance(number, int)
        assert number == ticket.number
        assert number > 0

    async def test_removes_ticket_row(self, real_db_session, ticket):
        ticket_id = ticket.id
        await tickets_service.delete_ticket(real_db_session, ticket=ticket)
        # Строка тикета исчезла.
        res = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == ticket_id)
        )
        assert res.scalar_one_or_none() is None

    async def test_cascade_removes_messages_and_attachments(self, real_db_session, real_user):
        """``ON DELETE CASCADE`` вычищает сообщения и вложения автоматически —
        без ручного DELETE. Создаём тикет с сообщением + attachment-записью,
        удаляем тикет, проверяем что дочерние строки ушли."""
        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(subject="Каскад", description="тело"),
            files=[],
        )
        ticket_id = ticket.id

        # Первое сообщение создаётся ``create_ticket``; добавим второе + вложение,
        # чтобы CASCADE был нетривиальным (несколько дочерних строк).
        second_msg = HelpdeskMessage(
            ticket_id=ticket_id,
            author_user_id=real_user.id,
            author_email=real_user.email,
            author_name=real_user.full_name,
            direction="inbound",
            body_text="дополнительный ответ",
            source="web",
        )
        real_db_session.add(second_msg)
        await real_db_session.flush()
        att = HelpdeskAttachment(
            ticket_id=ticket_id,
            message_id=second_msg.id,
            filename="deadbeef_file.pdf",
            original_name="file.pdf",
            content_type="application/pdf",
            size_bytes=42,
            is_inline=False,
        )
        real_db_session.add(att)
        await real_db_session.flush()
        # Refresh ticket: атрибуты могли expire после flush в SAVEPOINT-сессии.
        await real_db_session.refresh(ticket)

        await tickets_service.delete_ticket(real_db_session, ticket=ticket)

        msgs = (
            (
                await real_db_session.execute(
                    select(HelpdeskMessage).where(HelpdeskMessage.ticket_id == ticket_id)
                )
            )
            .scalars()
            .all()
        )
        assert msgs == []
        atts = (
            (
                await real_db_session.execute(
                    select(HelpdeskAttachment).where(HelpdeskAttachment.ticket_id == ticket_id)
                )
            )
            .scalars()
            .all()
        )
        assert atts == []

    async def test_fs_cleanup_called(self, real_db_session, ticket, monkeypatch):
        """``delete_ticket_dir`` вызывается с номером тикета до удаления строки
        (best-effort очистка папки ``/data/helpdesk/TKT-{number}``)."""
        calls: list[int] = []
        # Патчим функцию в модуле, где она импортируется (отложенный импорт внутри
        # delete_ticket берёт её из app.services.helpdesk.attachments).
        from app.services.helpdesk import attachments as att_mod

        monkeypatch.setattr(
            att_mod,
            "delete_ticket_dir",
            lambda n: calls.append(n),
        )
        number = await tickets_service.delete_ticket(real_db_session, ticket=ticket)
        assert calls == [number]


# ---------------------------------------------------------------------------
# Роутерный слой: DELETE /tickets/{id} — ACL (admin-only)
# ---------------------------------------------------------------------------


class TestDeleteTicketEndpoint:
    """Вызываем endpoint-функцию напрямую (как ``test_helpdesk_agents``),
    передавая ``real_admin``/``real_editor``/``real_user`` и мок-redis."""

    async def test_admin_deletes_returns_none(self, real_db_session, real_admin, ticket):
        from app.api.helpdesk.tickets import delete_ticket as delete_endpoint

        ticket_id = ticket.id
        # Refresh admin: в SAVEPOINT-сессии атрибуты могут expire после commit'ов
        # фикстур (как в test_add_list_delete_agent).
        await real_db_session.refresh(real_admin)
        result = await delete_endpoint(ticket_id, real_admin, real_db_session, _redis())
        # Endpoint возвращает 204 (None) — тело отсутствует.
        assert result is None
        # Тикета больше нет.
        res = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == ticket_id)
        )
        assert res.scalar_one_or_none() is None

    async def test_non_admin_role_gets_403_at_deps(self, real_db_session, real_editor):
        """Editor/reader/helpdesk-agent-без-admin-роли отсекаются зависимостью
        ``AdminDep`` (``require_admin`` → 403). Проверяем на уровне зависимости,
        т.к. endpoint-функция принимает уже авторизованного admin'а (зависимость
        резолвится FastAPI до вызова функции).

        ``require_admin`` — синхронная функция (внутри ``require_role`` возвращает
        coroutine ``_check``, но ``require_admin`` резолвит её через ``Depends``
        уже на этапе сборки зависимостей). Поэтому вызываем синхронно."""
        from app.api.deps import require_role

        # ``require_role("admin")`` возвращает ``_check`` — coroutine function,
        # которую FastAPI вызывает для резолва зависимости. Вызываем её напрямую
        # с не-admin пользователем — должна поднять 403.
        admin_check = require_role("admin")
        with pytest.raises(HTTPException) as exc:
            await admin_check(real_editor)
        assert exc.value.status_code == 403

    async def test_nonexistent_ticket_returns_404(self, real_db_session, real_admin):
        from app.api.helpdesk.tickets import delete_ticket as delete_endpoint

        await real_db_session.refresh(real_admin)
        with pytest.raises(HTTPException) as exc:
            await delete_endpoint(uuid.uuid4(), real_admin, real_db_session, _redis())
        assert exc.value.status_code == 404

    async def test_audit_event_pushed(self, real_db_session, real_admin, ticket):
        """Удаление фиксируется в журнале аудита как ``helpdesk.ticket_deleted``
        с метаданными (number/subject/previous_status) — единственный след
        операции (тихое удаление без уведомлений)."""
        from app.api.helpdesk.tickets import delete_ticket as delete_endpoint

        number = ticket.number
        subject = ticket.subject
        status = ticket.status
        await real_db_session.refresh(real_admin)
        redis_mock = _redis()
        await delete_endpoint(ticket.id, real_admin, real_db_session, redis_mock)
        # push_audit_event делает rpush в Redis-очередь аудита.
        assert redis_mock.rpush.await_count == 1
        _queue, payload = redis_mock.rpush.await_args.args
        # payload — JSON-строка; проверяем ключевые поля.
        import json

        data = json.loads(payload)
        assert data["event_type"] == "helpdesk.ticket_deleted"
        assert data["resource_type"] == "helpdesk_ticket"
        assert data["metadata"]["number"] == number
        assert data["metadata"]["subject"] == subject
        assert data["metadata"]["previous_status"] == status
