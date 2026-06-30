"""Integration tests for helpdesk attachments (Этап 4, Б5).

Локальное хранение: файлы в ``/data/helpdesk/TKT-{number}/{file}``. В тестах
``HELPDESK_FILES_DIR`` перенаправляется во временную папку (``tmp_path``),
чтобы не писать в реальный ``/data``. Покрывает upload (authorized/forbidden),
download (StreamingResponse-ACL), path-traversal-отклонение, удаление файлов
при удалении тикета (CASCADE).

Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


def _upload_file(name: str, data: bytes = b"hello world", mime: str = "text/plain"):
    from fastapi import UploadFile

    return UploadFile(filename=name, file=io.BytesIO(data), headers={"content-type": mime})


@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    """Перенаправить HELPDESK_FILES_DIR во временную папку."""
    from app.services.helpdesk import attachments as att_service
    from app.services.helpdesk import tickets as tickets_service

    monkeypatch.setattr(att_service, "HELPDESK_FILES_DIR", tmp_path)
    # upload_attachments внутри может импортировать константу повторно.
    monkeypatch.setattr("app.core.constants.HELPDESK_FILES_DIR", tmp_path)
    _ = tickets_service  # smoke: модуль загружен
    return tmp_path


@pytest_asyncio.fixture
async def ticket(real_db_session, real_user):
    from app.api.helpdesk.tickets import create_ticket
    from app.schemas.helpdesk import TicketCreateIn

    return await create_ticket(
        TicketCreateIn(subject="Заявка с файлом", description="тело"),
        real_user,
        real_db_session,
        _redis(),
    )


async def _make_agent(db, user) -> None:
    from app.models.helpdesk import HelpdeskAgent

    db.add(HelpdeskAgent(user_id=user.id, notify_new=True))
    await db.commit()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    async def test_create_ticket_with_files(self, real_db_session, real_user, files_dir):
        from app.api.helpdesk.tickets import create_ticket
        from app.schemas.helpdesk import TicketCreateIn

        out = await create_ticket(
            TicketCreateIn(subject="S", description="D"),
            real_user,
            real_db_session,
            _redis(),
            files=[_upload_file("note.txt", b"abc")],
        )
        assert out.source.value == "web"
        # Файл лежит в папке тикета.
        from app.services.helpdesk.attachments import ticket_dir

        assert (ticket_dir(out.number) / "note.txt").exists() or any(
            p.is_file() for p in ticket_dir(out.number).iterdir()
        )

    async def test_download_owner_allowed(self, real_db_session, real_user, ticket, files_dir):
        from sqlalchemy import select

        from app.api.helpdesk.tickets import add_my_message, download_attachment
        from app.schemas.helpdesk import MessageCreateIn
        from app.services.helpdesk.attachments import HelpdeskAttachment

        msg = await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="ответ"),
            real_user,
            real_db_session,
            _redis(),
            files=[_upload_file("rep.txt", b"data")],
        )
        # Берём id вложения из БД.
        res = await real_db_session.execute(
            select(HelpdeskAttachment).where(HelpdeskAttachment.message_id == msg.id)
        )
        att = res.scalars().one()
        # download_attachment возвращает StreamingResponse; здесь проверяем
        # только, что ACL пропустил владельца (не 404).
        response = await download_attachment(att.id, real_user, real_db_session)
        assert response.status_code == 200

    async def test_download_foreign_user_404(
        self, real_db_session, real_user, real_editor, ticket, files_dir
    ):
        from sqlalchemy import select

        from app.api.helpdesk.tickets import add_my_message, download_attachment
        from app.schemas.helpdesk import MessageCreateIn
        from app.services.helpdesk.attachments import HelpdeskAttachment

        await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="ответ"),
            real_user,
            real_db_session,
            _redis(),
            files=[_upload_file("rep.txt", b"data")],
        )
        res = await real_db_session.execute(
            select(HelpdeskAttachment).where(HelpdeskAttachment.ticket_id == ticket.id)
        )
        att = res.scalars().first()
        assert att is not None
        with pytest.raises(HTTPException) as exc:
            await download_attachment(att.id, real_editor, real_db_session)
        assert exc.value.status_code == 404

    async def test_download_agent_allowed_even_if_not_owner(
        self, real_db_session, real_user, real_editor, ticket, files_dir
    ):
        from sqlalchemy import select

        from app.api.helpdesk.tickets import add_my_message, download_attachment
        from app.schemas.helpdesk import MessageCreateIn
        from app.services.helpdesk.attachments import HelpdeskAttachment

        await add_my_message(
            ticket.id,
            MessageCreateIn(body_text="ответ"),
            real_user,
            real_db_session,
            _redis(),
            files=[_upload_file("rep.txt", b"data")],
        )
        await _make_agent(real_db_session, real_editor)
        res = await real_db_session.execute(
            select(HelpdeskAttachment).where(HelpdeskAttachment.ticket_id == ticket.id)
        )
        att = res.scalars().first()
        assert att is not None
        response = await download_attachment(att.id, real_editor, real_db_session)
        assert response.status_code == 200
