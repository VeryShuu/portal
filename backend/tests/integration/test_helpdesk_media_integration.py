"""Integration tests — Helpdesk inline-media (картинки rich-редактора ответов).

Проверяет media-endpoint (``POST`` upload + ``GET`` serve) по образцу
``test_kb_media_integration``: upload возвращает URL с ticket_id; serve отдаёт
``X-Accel-Redirect``; ACL — автор тикета или агент/админ, иначе 404; валидация
расширения/MIME; path-traversal guard.

Авто-skip'ается без ``INTEGRATION_DB=true``. Вызывает endpoint-функции напрямую
(не через HTTP) — это обходит module-gate на роутере и focus'ит логику media.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.api.helpdesk.media import (
    _is_helpdesk_agent,
    serve_ticket_inline_media,
    upload_ticket_inline_media,
)
from app.core.constants import HELPDESK_INLINE_IMAGE_MIMES

pytestmark = pytest.mark.asyncio


# ─── helpers ─────────────────────────────────────────────────────────────────


async def _create_db_user(db, role: str = "reader"):
    """Создать пользователя в БД. Дефолт ``role="reader"`` — канонический
    «обычный пользователь» (в ``ck_users_role`` валидны только reader/editor/admin;
    роли ``user`` не существует)."""
    from app.models.user import User

    u = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@portal.local",
        full_name=f"Integration {role.title()}",
        department="IT",
        role=role,
        auth_source="local",
        password_hash=None,
        presence_status="office",
        notify_email=False,
        notify_inapp=False,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _create_db_ticket(db, requester_id: uuid.UUID):
    """Создать тикет. ``number`` генерируется БД (``GENERATED ALWAYS AS IDENTITY`` —
    явная вставка запрещена); читаем через ``ticket.number`` после commit."""
    from app.models.helpdesk import HelpdeskTicket

    t = HelpdeskTicket(
        subject="Тикет media-test",
        description="test",
        description_html=None,
        status="new",
        source="web",
        requester_user_id=requester_id,
        requester_email="requester@portal.local",
        requester_name="Заявитель",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


def _make_upload_file(filename: str, content_type: str, data: bytes):
    """Минимальный UploadFile-подобный объект для stream_upload_to_path (мок)."""
    from types import SimpleNamespace

    return SimpleNamespace(
        filename=filename,
        content_type=content_type,
        read=AsyncMock(side_effect=[data, b""]),
    )


def _fake_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    return r


# Минимальный валидный JPEG-хвост (magic-байты) — stream_upload_to_path мокается,
# но MIME-валидация в реальном коде смотрит на magic.from_buffer; мы мокаем весь
# stream_upload_to_path, поэтому содержимое не критично.
_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


# ─── is_helpdesk_agent ──────────────────────────────────────────────────────


class TestIsHelpdeskAgent:
    async def test_admin_is_agent(self, real_db_session):
        from app.models.user import User

        admin = User(
            email=f"admin-{uuid.uuid4().hex[:6]}@portal.local",
            full_name="Admin",
            role="admin",
            auth_source="local",
            password_hash=None,
            lang="ru",
            preferences={},
        )
        real_db_session.add(admin)
        await real_db_session.commit()
        await real_db_session.refresh(admin)
        assert await _is_helpdesk_agent(real_db_session, user=admin) is True

    async def test_plain_user_not_agent(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        assert await _is_helpdesk_agent(real_db_session, user=u) is False

    async def test_helpdesk_agent_member(self, real_db_session):
        from app.models.helpdesk import HelpdeskAgent

        u = await _create_db_user(real_db_session, role="reader")
        real_db_session.add(HelpdeskAgent(user_id=u.id, added_by=u.id))
        await real_db_session.commit()
        assert await _is_helpdesk_agent(real_db_session, user=u) is True


# ─── upload ──────────────────────────────────────────────────────────────────


class TestUploadInlineMedia:
    async def test_author_can_upload_and_gets_url(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        upload_file = _make_upload_file("screen.jpg", "image/jpeg", _JPEG_BYTES)
        with patch(
            "app.api.helpdesk.media.stream_upload_to_path", new_callable=AsyncMock
        ) as mock_upload:
            mock_upload.return_value = (len(_JPEG_BYTES), "image/jpeg")
            out = await upload_ticket_inline_media(
                ticket.id, upload_file, real_db_session, u, _fake_redis()
            )

        assert "/inline-media/" in out.url
        assert str(ticket.id) in out.url
        assert out.filename.endswith("_screen.jpg")
        # stream_upload вызван с правильным max_size и allowed_mimes.
        mock_upload.assert_awaited_once()
        kwargs = mock_upload.call_args.kwargs
        assert kwargs["allowed_mimes"] == HELPDESK_INLINE_IMAGE_MIMES

    async def test_other_user_cannot_upload_to_foreign_ticket(self, real_db_session):
        owner = await _create_db_user(real_db_session, role="reader")
        stranger = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, owner.id)

        upload_file = _make_upload_file("x.jpg", "image/jpeg", _JPEG_BYTES)
        with pytest.raises(HTTPException) as exc:
            await upload_ticket_inline_media(
                ticket.id, upload_file, real_db_session, stranger, _fake_redis()
            )
        assert exc.value.status_code == 404

    async def test_bad_extension_rejected(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        upload_file = _make_upload_file("doc.exe", "application/octet-stream", b"MZ")
        with pytest.raises(HTTPException) as exc:
            await upload_ticket_inline_media(
                ticket.id, upload_file, real_db_session, u, _fake_redis()
            )
        assert exc.value.status_code == 400

    async def test_too_large_raises_413(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        upload_file = _make_upload_file("big.jpg", "image/jpeg", _JPEG_BYTES)
        with patch(
            "app.api.helpdesk.media.stream_upload_to_path", new_callable=AsyncMock
        ) as mock_upload:
            mock_upload.side_effect = HTTPException(status_code=413, detail="too large")
            with pytest.raises(HTTPException) as exc:
                await upload_ticket_inline_media(
                    ticket.id, upload_file, real_db_session, u, _fake_redis()
                )
        assert exc.value.status_code == 413


# ─── serve ───────────────────────────────────────────────────────────────────


class TestServeInlineMedia:
    async def test_author_gets_x_accel_redirect(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        filename = f"{uuid.uuid4().hex[:8]}_screen.png"
        resp = await serve_ticket_inline_media(
            ticket.id, filename, real_db_session, u, _fake_redis()
        )
        assert isinstance(resp, Response)
        assert resp.headers["X-Accel-Redirect"] == (
            f"/internal/helpdesk-media/TKT-{ticket.number}/inline/{filename}"
        )
        assert resp.headers["Content-Type"] == "image/png"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    async def test_stranger_gets_404(self, real_db_session):
        owner = await _create_db_user(real_db_session, role="reader")
        stranger = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, owner.id)

        with pytest.raises(HTTPException) as exc:
            await serve_ticket_inline_media(
                ticket.id, "abc_img.png", real_db_session, stranger, _fake_redis()
            )
        assert exc.value.status_code == 404

    async def test_path_traversal_rejected(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        # Тикет доступен (автор), но имя файла — path-traversal.
        with pytest.raises(HTTPException) as exc:
            await serve_ticket_inline_media(
                ticket.id, "../../etc/passwd", real_db_session, u, _fake_redis()
            )
        assert exc.value.status_code == 400

    async def test_slash_in_filename_rejected(self, real_db_session):
        u = await _create_db_user(real_db_session, role="reader")
        ticket = await _create_db_ticket(real_db_session, u.id)

        with pytest.raises(HTTPException) as exc:
            await serve_ticket_inline_media(
                ticket.id, "sub/dir_img.png", real_db_session, u, _fake_redis()
            )
        assert exc.value.status_code == 400
