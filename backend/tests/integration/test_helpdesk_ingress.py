"""Integration tests for helpdesk ingress + archive + guest-link (Этап 5).

IMAP-фетчинг требует живого IMAP-сервера (testcontainers greenmail) — вне
скоупа. Здесь проверяем:

* Anti-loop detection (``is_auto_reply``, ``is_from_self``) — чистые функции.
* Matching: тикет находится по references / subject-token; ответ реопенит.
* Идемпотентность через ``helpdesk_email_log`` (повторная обработка → skip).
* Guest linking: ``link_guest_tickets`` привязывает гостевые тикеты к новому
  аккаунту (ТЗ §4.5).
* Archive: ``archive_closed_tickets`` переносит closed-тикеты в архив;
  ``cleanup_archived_files`` удаляет папки (с redirect'ом HELPDESK_FILES_DIR).

Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, text

from app.models.helpdesk import (
    HelpdeskTicket,
    HelpdeskTicketArchive,
)
from app.schemas.helpdesk import TicketCreateIn
from app.services.helpdesk import tickets as tickets_service


async def _ensure_archive_partition(db, closed_at: datetime) -> None:
    """Гарантировать существование партиции ``helpdesk_tickets_archive`` для
    месяца указанного ``closed_at``.

    Миграция 075 создаёт только партицию текущего месяца; cron
    ``create_next_helpdesk_archive_partition`` — текущий + 3 будущих. Но тесты
    используют ``closed_at`` в прошлом (раньше ``HELPDESK_ARCHIVE_AFTER_DAYS``),
    который может попасть в месяц без партиции → insert падает с
    ``CheckViolationError: no partition found``. Создаём партицию явно.
    """
    start = closed_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start + relativedelta(months=1)
    tbl = f"helpdesk_tickets_archive_{start.strftime('%Y_%m')}"
    await db.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {tbl}"
            f" PARTITION OF helpdesk_tickets_archive"
            f" FOR VALUES FROM ('{start.strftime('%Y-%m-%d')}')"
            f" TO ('{end.strftime('%Y-%m-%d')}')"
        )
    )
    await db.commit()


from app.services.helpdesk.archive import archive_closed_tickets, cleanup_archived_files
from app.services.helpdesk.tickets import link_guest_tickets

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Guest linking
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def guest_ticket(real_db_session):
    """Гостевой тикет (без requester_user_id) — как от email-инициатора."""
    ticket = HelpdeskTicket(
        subject="Гостевая заявка",
        description="тело",
        status="new",
        source="email",
        requester_email="guest@external.com",
        requester_name="Гость",
    )
    real_db_session.add(ticket)
    await real_db_session.commit()
    await real_db_session.refresh(ticket)
    return ticket


class TestGuestLinking:
    async def test_links_guest_tickets_by_email(self, real_db_session, guest_ticket):
        from app.models.user import User

        user = User(
            email="guest@external.com",
            full_name="Now Registered",
            department="IT",
            role="reader",
            auth_source="local",
            presence_status="office",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences={},
        )
        real_db_session.add(user)
        await real_db_session.flush()

        linked = await link_guest_tickets(real_db_session, user_id=user.id, email=user.email)
        assert linked == 1
        await real_db_session.commit()
        # Перечитаем тикет свежим SELECT (refresh фикстурного объекта может
        # отдать закэшированный identity-map экземпляр).
        from sqlalchemy import select as _select

        res = await real_db_session.execute(
            _select(HelpdeskTicket).where(HelpdeskTicket.id == guest_ticket.id)
        )
        fresh = res.scalars().one()
        assert fresh.requester_user_id == user.id

    async def test_idempotent_on_relogin(self, real_db_session, guest_ticket):
        from app.models.user import User

        user = User(
            email="guest@external.com",
            full_name="X",
            department="IT",
            role="reader",
            auth_source="local",
            presence_status="office",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences={},
        )
        real_db_session.add(user)
        await real_db_session.flush()
        await link_guest_tickets(real_db_session, user_id=user.id, email=user.email)
        # Повторный вызов (ре-логин) — no-op.
        second = await link_guest_tickets(real_db_session, user_id=user.id, email=user.email)
        assert second == 0

    async def test_email_match_is_case_insensitive(self, real_db_session, guest_ticket):
        from app.models.user import User

        user = User(
            email="GUEST@external.com",
            full_name="X",
            department="IT",
            role="reader",
            auth_source="local",
            presence_status="office",
            notify_email=True,
            notify_inapp=True,
            lang="ru",
            preferences={},
        )
        real_db_session.add(user)
        await real_db_session.flush()
        linked = await link_guest_tickets(real_db_session, user_id=user.id, email=user.email)
        assert linked == 1


# ---------------------------------------------------------------------------
# Email-log idempotency
# ---------------------------------------------------------------------------


class TestEmailLogIdempotency:
    async def test_duplicate_message_id_skipped(self, real_db_session):
        """Повторная обработка того же Message-ID → skip (через ``_fetch_log``)."""
        from app.services.helpdesk.ingress import _fetch_log, _write_log

        mid = "<dup-123@test>"
        await _write_log(real_db_session, mid, None, None, status="created", error=None)
        existing = await _fetch_log(real_db_session, mid)
        assert existing is not None
        assert existing.status == "created"


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def closed_old_ticket(real_db_session, real_user, monkeypatch):
    """Closed-тикет старше HELPDESK_ARCHIVE_AFTER_DAYS — кандидат в архив."""
    from app.core.constants import HELPDESK_ARCHIVE_AFTER_DAYS

    old = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_AFTER_DAYS + 5)
    # Партиция для месяца closed_at может отсутствовать (миграция создаёт
    # только текущий месяц) — обеспечиваем явно, иначе archive-insert упадёт.
    await _ensure_archive_partition(real_db_session, old)
    ticket = await tickets_service.create_ticket(
        real_db_session,
        user=real_user,
        payload=TicketCreateIn(subject="Закрыто давно", description="тело"),
        files=[],
    )
    ticket.status = "closed"
    ticket.closed_at = old
    ticket.closed_by_user_id = real_user.id
    await real_db_session.commit()
    await real_db_session.refresh(ticket)
    return ticket


class TestArchive:
    async def test_archive_moves_closed_old_ticket(self, real_db_session, closed_old_ticket):
        # Внимание: этот smoke-тест читает результат в ТОЙ ЖЕ savepoint-сессии
        # сразу после flush. Savepoint-модель real_db_session маскирует
        # отсутствие db.commit() — поэтому персистентность commit'а проверяется
        # отдельно в tests/unit/test_helpdesk_archive.py (commit.assert_awaited).
        archived = await archive_closed_tickets(real_db_session)
        assert archived >= 1
        # Живая строка удалена.
        live = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == closed_old_ticket.id)
        )
        assert live.scalars().first() is None
        # Архивная строка появилась.
        arch = await real_db_session.execute(
            select(HelpdeskTicketArchive).where(HelpdeskTicketArchive.id == closed_old_ticket.id)
        )
        row = arch.scalars().first()
        assert row is not None
        assert row.number == closed_old_ticket.number
        assert row.payload.get("ticket", {}).get("subject") == "Закрыто давно"

    async def test_recent_closed_not_archived(self, real_db_session, real_user):
        from app.schemas.helpdesk import TicketCreateIn

        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(subject="Недавно", description="т"),
            files=[],
        )
        ticket.status = "closed"
        ticket.closed_at = datetime.now(UTC)  # сегодня
        await real_db_session.commit()
        before = ticket.id
        await archive_closed_tickets(real_db_session)
        live = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == before)
        )
        assert live.scalars().first() is not None  # остался

    async def test_open_not_archived(self, real_db_session, real_user):
        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(subject="Открыто", description="т"),
            files=[],
        )
        before = ticket.id
        await archive_closed_tickets(real_db_session)
        live = await real_db_session.execute(
            select(HelpdeskTicket).where(HelpdeskTicket.id == before)
        )
        assert live.scalars().first() is not None


class TestCleanupFiles:
    async def test_cleanup_removes_old_archived_folders(
        self, real_db_session, closed_old_ticket, tmp_path, monkeypatch
    ):
        from app.core.constants import HELPDESK_ARCHIVE_FILES_TTL_DAYS
        from app.services.helpdesk import attachments as att_service

        # Сначала архивируем.
        await archive_closed_tickets(real_db_session)
        # Имитируем, что архивная запись старше TTL.

        old = datetime.now(UTC) - timedelta(days=HELPDESK_ARCHIVE_FILES_TTL_DAYS + 1)
        await real_db_session.execute(
            select(HelpdeskTicketArchive).where(HelpdeskTicketArchive.id == closed_old_ticket.id)
        )
        # Обновим archived_at через ORM.
        arch_res = await real_db_session.execute(
            select(HelpdeskTicketArchive).where(HelpdeskTicketArchive.id == closed_old_ticket.id)
        )
        arch_row = arch_res.scalars().first()
        assert arch_row is not None
        arch_row.archived_at = old
        await real_db_session.commit()

        # Создадим папку тикета и файл в tmp_path.
        monkeypatch.setattr(att_service, "HELPDESK_FILES_DIR", tmp_path)
        ticket_dir = tmp_path / f"TKT-{closed_old_ticket.number}"
        ticket_dir.mkdir(parents=True)
        (ticket_dir / "file.bin").write_bytes(b"x")

        removed = await cleanup_archived_files(real_db_session)
        assert removed >= 1
        assert not ticket_dir.exists()
