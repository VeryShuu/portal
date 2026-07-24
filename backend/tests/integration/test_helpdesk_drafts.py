"""Integration tests for helpdesk draft-attachments (Этап 3).

Draft-attachments bridge the chicken-and-egg gap: inline images uploaded
through the ticket **creation** form have no ``ticket_id`` yet, so they are
staged as drafts and backfilled into the ticket's permanent inline folder on
``create_ticket``.

Covers the full lifecycle at the service layer:
- ``create_draft_attachment``: upload → row + file on disk, per-user limit.
- ``backfill_draft_images`` via ``create_ticket``: draft URL → inline-media URL,
  file moved, draft row deleted, inline ``HelpdeskAttachment`` created.
- Backward compat: tickets without draft URLs are unaffected.

FS writes go to ``tmp_path`` (via monkeypatched ``HELPDESK_FILES_DIR``) so the
real ``/data/helpdesk`` is never touched. Auto-skipped without ``INTEGRATION_DB``.
"""

from __future__ import annotations

import io
from typing import Any, cast

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from app.models.helpdesk import HelpdeskAttachment, HelpdeskDraftAttachment
from app.schemas.helpdesk import TicketCreateIn
from app.services.helpdesk import drafts as drafts_service
from app.services.helpdesk import tickets as tickets_service

pytestmark = pytest.mark.asyncio


# Minimal 1×1 PNG (valid magic bytes for ``python-magic`` → image/png).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c636000000000020001e221bc330000000049454e44ae426082"
)


def _png_upload(name: str = "screen.png") -> UploadFile:
    return UploadFile(
        filename=name,
        file=io.BytesIO(_PNG_BYTES),
        headers=cast("Any", {"content-type": "image/png"}),
    )


@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    """Redirect HELPDESK_FILES_DIR to a tmp dir for both the drafts service and
    the attachments service (the backfill writes inline files via the latter)."""
    from app.services.helpdesk import attachments as att_service

    monkeypatch.setattr(drafts_service, "HELPDESK_FILES_DIR", tmp_path)
    monkeypatch.setattr(att_service, "HELPDESK_FILES_DIR", tmp_path)
    monkeypatch.setattr("app.core.constants.HELPDESK_FILES_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# create_draft_attachment
# ---------------------------------------------------------------------------


class TestCreateDraftAttachment:
    async def test_creates_draft_row_and_file(self, real_db_session, real_user, files_dir):
        draft = await drafts_service.create_draft_attachment(
            real_db_session, user=real_user, file=_png_upload()
        )
        assert draft.uploaded_by_user_id == real_user.id
        assert draft.content_type == "image/png"
        assert draft.size_bytes == len(_PNG_BYTES)

        # File on disk under the user's draft folder.
        disk = drafts_service.draft_dir(real_user.id) / draft.filename
        assert disk.is_file()
        assert disk.read_bytes() == _PNG_BYTES

    async def test_rejects_non_image_mime(self, real_db_session, real_user, files_dir):
        """``stream_upload_to_path`` checks real MIME via libmagic and rejects
        non-images (422). The extension guard itself lives in the router and is
        covered by unit tests; here we exercise the service-level MIME check."""
        from fastapi import HTTPException

        bogus = UploadFile(
            filename="fake.png",
            file=io.BytesIO(b"<html>not an image</html>"),
            headers=cast("Any", {"content-type": "image/png"}),
        )
        with pytest.raises(HTTPException) as exc:
            await drafts_service.create_draft_attachment(
                real_db_session, user=real_user, file=bogus
            )
        assert exc.value.status_code == 422

    async def test_enforces_per_user_limit(
        self, real_db_session, real_user, files_dir, monkeypatch
    ):
        from fastapi import HTTPException

        # Lower the limit so the test is fast.
        monkeypatch.setattr(drafts_service, "HELPDESK_DRAFT_MAX_PER_USER", 2)
        for _ in range(2):
            await drafts_service.create_draft_attachment(
                real_db_session, user=real_user, file=_png_upload()
            )
        with pytest.raises(HTTPException) as exc:
            await drafts_service.create_draft_attachment(
                real_db_session, user=real_user, file=_png_upload()
            )
        assert exc.value.status_code == 409

    async def test_get_draft_owner_only(self, real_db_session, real_user, real_editor, files_dir):
        draft = await drafts_service.create_draft_attachment(
            real_db_session, user=real_user, file=_png_upload()
        )
        mine = await drafts_service.get_draft_for_user(
            real_db_session, draft_id=draft.id, user_id=real_user.id
        )
        assert mine is not None and mine.id == draft.id
        # Another user cannot fetch it (→ None, router maps to 404).
        foreign = await drafts_service.get_draft_for_user(
            real_db_session, draft_id=draft.id, user_id=real_editor.id
        )
        assert foreign is None


# ---------------------------------------------------------------------------
# backfill via create_ticket
# ---------------------------------------------------------------------------


class TestBackfillDraftImages:
    async def test_draft_urls_rewritten_to_inline_media(
        self, real_db_session, real_user, files_dir
    ):
        """End-to-end: create two drafts → build description_html referencing them
        → create_ticket → assert src rewritten, files moved, drafts deleted."""
        d1 = await drafts_service.create_draft_attachment(
            real_db_session, user=real_user, file=_png_upload("a.png")
        )
        d2 = await drafts_service.create_draft_attachment(
            real_db_session, user=real_user, file=_png_upload("b.png")
        )
        description_html = (
            f"<p>Скриншоты:</p>"
            f'<p><img src="/api/v1/helpdesk/draft-attachments/{d1.id}"></p>'
            f'<p><img src="/api/v1/helpdesk/draft-attachments/{d2.id}"></p>'
        )
        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(
                subject="С ошибкой",
                description="Скриншоты ниже",
                description_html=description_html,
            ),
            files=[],
        )
        # Both draft URLs replaced with inline-media URLs.
        assert "draft-attachments" not in (ticket.description_html or "")
        assert f"/api/v1/helpdesk/tickets/{ticket.id}/inline-media/" in (
            ticket.description_html or ""
        )

        full = await tickets_service.fetch_ticket_for_user(
            real_db_session, ticket_id=ticket.id, user_id=real_user.id
        )
        assert full is not None
        first = full.messages[0]
        assert first.body_html == ticket.description_html

        # Two inline attachments created for the first message.
        atts = (
            (
                await real_db_session.execute(
                    select(HelpdeskAttachment).where(HelpdeskAttachment.message_id == first.id)
                )
            )
            .scalars()
            .all()
        )
        inline = [a for a in atts if a.is_inline]
        assert len(inline) == 2

        # Draft rows deleted (backfilled atomically).
        remaining = (
            (
                await real_db_session.execute(
                    select(HelpdeskDraftAttachment).where(
                        HelpdeskDraftAttachment.id.in_([d1.id, d2.id])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining == []

        # Draft files removed from the drafts folder.
        assert not (drafts_service.draft_dir(real_user.id) / d1.filename).exists()
        assert not (drafts_service.draft_dir(real_user.id) / d2.filename).exists()

    async def test_ticket_without_drafts_unaffected(self, real_db_session, real_user, files_dir):
        """Backward compat: description_html without draft URLs passes through."""
        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(
                subject="Без картинок",
                description="Просто текст",
                description_html="<p>Просто <em>текст</em></p>",
            ),
            files=[],
        )
        assert ticket.description_html == "<p>Просто <em>текст</em></p>"

    async def test_missing_draft_left_as_is(self, real_db_session, real_user, files_dir):
        """Best-effort: a draft-id that doesn't exist (or isn't owned by the user)
        is left untouched — the ticket is still created."""
        bogus = "00000000-0000-0000-0000-000000000000"
        description_html = f'<p><img src="/api/v1/helpdesk/draft-attachments/{bogus}"></p>'
        ticket = await tickets_service.create_ticket(
            real_db_session,
            user=real_user,
            payload=TicketCreateIn(
                subject="Битый draft",
                description="текст",
                description_html=description_html,
            ),
            files=[],
        )
        # The bogus draft URL is preserved (not silently dropped).
        assert bogus in (ticket.description_html or "")


# ---------------------------------------------------------------------------
# cleanup_expired_drafts
# ---------------------------------------------------------------------------


class TestCleanupExpiredDrafts:
    async def test_purges_old_drafts_keeps_fresh(
        self, real_db_session, real_user, files_dir, monkeypatch
    ):
        from datetime import UTC, datetime, timedelta

        from app.models.helpdesk import HelpdeskDraftAttachment

        # An "old" draft row whose created_at is beyond the TTL.
        old = HelpdeskDraftAttachment(
            uploaded_by_user_id=real_user.id,
            filename="old.png",
            original_name="old.png",
            content_type="image/png",
            size_bytes=10,
            created_at=datetime.now(UTC) - timedelta(hours=48),
        )
        real_db_session.add(old)
        await real_db_session.flush()
        # Write its bytes so cleanup can unlink them.
        old_path = drafts_service.draft_dir(real_user.id) / "old.png"
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_bytes(b"old-bytes")

        # A "fresh" draft that must survive.
        fresh = await drafts_service.create_draft_attachment(
            real_db_session, user=real_user, file=_png_upload("fresh.png")
        )

        removed = await drafts_service.cleanup_expired_drafts(real_db_session)
        assert removed == 1
        assert not old_path.exists()
        # Fresh draft intact.
        fresh_again = await drafts_service.get_draft_for_user(
            real_db_session, draft_id=fresh.id, user_id=real_user.id
        )
        assert fresh_again is not None


# ---------------------------------------------------------------------------
# Router commit invariant (regression)
# ---------------------------------------------------------------------------


@pytest.fixture
def _independent_engine():
    """A *real* engine (not the SAVEPOINT-wrapped ``real_db_session``) so writes
    survive the request — mirroring production ``get_db()`` (``autocommit=False``,
    no auto-commit on close). Used to prove the router actually commits."""
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    if os.environ.get("INTEGRATION_DB", "false").lower() not in ("1", "true", "yes"):
        pytest.skip("INTEGRATION_DB=true required")
    engine = create_async_engine(_db_url(), pool_pre_ping=True)
    yield engine


def _db_url() -> str:
    from app.core.config import get_settings

    return get_settings().database_url


class TestRouterCommitsToDatabase:
    """Regression for the 2026-07-22 bug: ``POST /draft-attachments`` returned a
    valid ``id`` but the row was never committed (``get_db`` has
    ``autocommit=False`` and only ``close()``s on exit), so the follow-up GET → 404.

    The SAVEPOINT-based ``real_db_session`` fixture masks this — its ``real_user``
    setup commits, accidentally persisting rows created in the same test. Here we
    exercise the real router handler against an independent engine and confirm the
    row is visible from a *fresh* session opened afterwards. This test fails the
    moment someone removes ``await db.commit()`` from ``upload_draft_attachment``.
    """

    async def test_uploaded_draft_visible_from_fresh_session(self, _independent_engine, files_dir):
        import uuid as _uuid

        from sqlalchemy.ext.asyncio import AsyncSession

        from app.api.helpdesk.drafts import upload_draft_attachment
        from app.models.helpdesk import HelpdeskDraftAttachment
        from app.models.user import User

        uid = _uuid.uuid4()
        from datetime import UTC, datetime

        async with AsyncSession(_independent_engine, expire_on_commit=False) as s:
            s.add(
                User(
                    id=uid,
                    email=f"draft-commit-{uid.hex[:8]}@test.local",
                    full_name="Commit Test",
                    role="reader",
                    auth_source="local",
                    presence_status="office",
                    notify_email=True,
                    notify_inapp=True,
                    lang="ru",
                    preferences={},
                    updated_at=datetime.now(UTC),
                )
            )
            await s.commit()

        try:
            # Simulate the request: a session that does NOT auto-commit (as get_db).
            from unittest.mock import AsyncMock

            from app.models.user import User as UserModel

            async with AsyncSession(_independent_engine, expire_on_commit=False) as req_session:
                req_user = (
                    await req_session.execute(select(UserModel).where(UserModel.id == uid))
                ).scalar_one()
                resp = await upload_draft_attachment(
                    file=_png_upload(),
                    db=req_session,
                    user=req_user,
                    redis=AsyncMock(),
                )
            assert resp.url, "router must return a servable URL"

            # Fresh session, independent of the request — row must be persisted.
            async with AsyncSession(_independent_engine, expire_on_commit=False) as checker:
                from sqlalchemy import select as _select

                draft_id = _uuid.UUID(resp.url.rsplit("/", 1)[-1])
                row = (
                    await checker.execute(
                        _select(HelpdeskDraftAttachment).where(
                            HelpdeskDraftAttachment.id == draft_id
                        )
                    )
                ).scalar_one_or_none()
            assert row is not None, (
                "draft row not visible from a fresh session — router forgot to commit "
                "(regression of 2026-07-22: POST returned id but GET → 404)"
            )
        finally:
            from sqlalchemy import text

            async with AsyncSession(_independent_engine) as s:
                await s.execute(
                    text("DELETE FROM helpdesk_draft_attachments WHERE uploaded_by_user_id = :u"),
                    {"u": uid},
                )
                await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
                await s.commit()
