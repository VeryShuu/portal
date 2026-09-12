"""Integration tests for helpdesk attachments (Этап 4).

Локальное хранение: файлы в ``/data/helpdesk/TKT-{number}/{file}``. В тестах
``HELPDESK_FILES_DIR`` перенаправляется во временную папку (``tmp_path``),
чтобы не писать в реальный ``/data``.

Upload/create тестируются через **сервисный слой** (``UploadFile`` передаётся
как обычный аргумент — это не Form-зависимость). Download — через роутер
``download_attachment`` (он не multipart: принимает attachment_id + user + db
и возвращает StreamingResponse; ACL-проверка в сервисе ``fetch_for_download``
кидает HTTPException 404 при нарушении).

Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.schemas.helpdesk import MessageCreateIn, TicketCreateIn
from app.services.helpdesk import messages as messages_service
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


def _upload_file(name: str, data: bytes = b"hello world", mime: str = "text/plain"):
    from typing import Any, cast

    from fastapi import UploadFile

    return UploadFile(
        filename=name, file=io.BytesIO(data), headers=cast("Any", {"content-type": mime})
    )


@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    """Перенаправить HELPDESK_FILES_DIR во временную папку."""
    from app.services.helpdesk import attachments as att_service

    monkeypatch.setattr(att_service, "HELPDESK_FILES_DIR", tmp_path)
    monkeypatch.setattr("app.core.constants.HELPDESK_FILES_DIR", tmp_path)
    return tmp_path


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    return await tickets_service.create_ticket(
        real_db_session,
        user=real_user,
        payload=TicketCreateIn(subject="Заявка с файлом", description="тело"),
        files=[],
    )


async def _make_agent(db, user) -> None:
    from app.models.helpdesk import HelpdeskAgent

    db.add(HelpdeskAgent(user_id=user.id, notify_new=True))
    await db.commit()


# ---------------------------------------------------------------------------
# Upload (через сервис)
# ---------------------------------------------------------------------------


class TestUpload:
    async def test_create_ticket_with_files(self, real_db_session, real_user, files_dir):
        from app.services.helpdesk.attachments import ticket_dir

        out = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(subject="S", description="D"),
            files=[_upload_file("note.txt", b"abc")],
        )
        assert out.source == "web"
        # Файл лежит в папке тикета (имя с uuid-префиксом).
        written = list(ticket_dir(out.number).iterdir())
        assert len(written) == 1
        assert written[0].read_bytes() == b"abc"

    async def test_reply_with_files_creates_attachment(
        self, real_db_session, real_user, ticket, files_dir
    ):
        from sqlalchemy import select

        from app.models.helpdesk import HelpdeskAttachment

        msg = await messages_service.add_requester_reply(
            real_db_session,
            ticket=ticket,
            user=real_user,
            payload=MessageCreateIn(body_text="ответ"),
            files=[_upload_file("rep.txt", b"data")],
        )
        res = await real_db_session.execute(
            select(HelpdeskAttachment).where(HelpdeskAttachment.message_id == msg.id)
        )
        att = res.scalars().one()
        assert att.original_name == "rep.txt"
        assert att.size_bytes == 4
        assert att.content_type == "text/plain"


# ---------------------------------------------------------------------------
# Download ACL (через роутер download_attachment — не multipart)
# ---------------------------------------------------------------------------


class TestDownloadAcl:
    async def _create_reply_attachment(self, db, user, ticket):
        await messages_service.add_requester_reply(
            db,
            ticket=ticket,
            user=user,
            payload=MessageCreateIn(body_text="ответ"),
            files=[_upload_file("rep.txt", b"data")],
        )
        from sqlalchemy import select

        from app.models.helpdesk import HelpdeskAttachment

        res = await db.execute(
            select(HelpdeskAttachment).where(HelpdeskAttachment.ticket_id == ticket.id)
        )
        return res.scalars().first()

    async def test_download_owner_allowed(self, real_db_session, real_user, ticket, files_dir):
        from app.api.helpdesk.tickets import download_attachment

        att = await self._create_reply_attachment(real_db_session, real_user, ticket)
        assert att is not None
        response = await download_attachment(att.id, real_user, real_db_session)
        assert response.status_code == 200

    async def test_download_foreign_user_404(
        self, real_db_session, real_user, real_editor, ticket, files_dir
    ):
        from app.api.helpdesk.tickets import download_attachment

        att = await self._create_reply_attachment(real_db_session, real_user, ticket)
        assert att is not None
        with pytest.raises(HTTPException) as exc:
            await download_attachment(att.id, real_editor, real_db_session)
        assert exc.value.status_code == 404

    async def test_download_agent_allowed_even_if_not_owner(
        self, real_db_session, real_user, real_editor, ticket, files_dir
    ):
        from app.api.helpdesk.tickets import download_attachment

        att = await self._create_reply_attachment(real_db_session, real_user, ticket)
        assert att is not None
        await _make_agent(real_db_session, real_editor)
        response = await download_attachment(att.id, real_editor, real_db_session)
        assert response.status_code == 200
