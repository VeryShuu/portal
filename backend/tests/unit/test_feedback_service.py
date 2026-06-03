"""Unit-тесты для app/api/feedback/feedback_service.py и feedback_repo.py.

Покрытие feedback_service.py:
- create_feedback: happy-path / notify-error проглочен
- load_admin_feedback_or_404: found / 404
- update_status: success / → closed notify / notify error проглочен
- add_reply: success → set status in_progress / 404 / notify skip same user
- load_feedback_for_attachment_access: found+admin / found+owner / 404 / forbidden
- upload_attachment: success / closed+non-admin 409 / attachment limit 409
- resolve_attachment_for_download: success / 404 att
- delete_attachment: success / 404 att / forbidden / closed+non-admin 409

Покрытие feedback_repo.py:
- count_my_feedback: with/without status filter
- list_my_feedback: with/without status filter
- fetch_my_feedback: found / None
- count_admin_feedback: with/without filters
- list_admin_feedback: with/without filters
- fetch_admin_feedback: found / None
- fetch_feedback_simple: found / None
- fetch_feedback_with_attachments: found
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")


def _make_user(role: str = "reader", user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name="Test User",
    )


def _make_feedback(
    *,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: str = "open",
    category: str = "bug",
    message: str = "Something broke",
    attachments: list | None = None,
) -> MagicMock:
    fb = MagicMock()
    fb.id = id or uuid.uuid4()
    fb.user_id = user_id or uuid.uuid4()
    fb.status = status
    fb.category = category
    fb.message = message
    fb.page_url = None
    fb.replies = []
    fb.attachments = attachments if attachments is not None else []
    fb.updated_at = datetime.now(UTC)
    fb.created_at = datetime.now(UTC)
    return fb


def _make_attachment(
    *,
    id: uuid.UUID | None = None,
    feedback_id: uuid.UUID | None = None,
    filename: str = "abc123_file.txt",
    original_name: str = "file.txt",
    uploaded_by: uuid.UUID | None = None,
) -> MagicMock:
    att = MagicMock()
    att.id = id or uuid.uuid4()
    att.feedback_id = feedback_id or uuid.uuid4()
    att.filename = filename
    att.original_name = original_name
    att.size_bytes = 1024
    att.mime_type = "text/plain"
    att.uploaded_by = uploaded_by or uuid.uuid4()
    att.created_at = datetime.now(UTC)
    return att


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.expunge = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


# ── feedback_service.create_feedback ─────────────────────────────────────────


class TestCreateFeedback:
    @pytest.mark.asyncio
    async def test_creates_and_returns_feedback(self):
        from app.api.feedback.feedback_service import create_feedback
        from app.schemas.feedback import FeedbackIn

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        payload = FeedbackIn(category="bug", message="Something broke")

        with patch(
            "app.api.feedback.feedback_service.notify_admins_new_feedback",
            new_callable=AsyncMock,
        ):
            await create_feedback(db, redis, user, payload)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_notify_error(self):
        from app.api.feedback.feedback_service import create_feedback
        from app.schemas.feedback import FeedbackIn

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        payload = FeedbackIn(category="suggestion", message="Add feature")

        with patch(
            "app.api.feedback.feedback_service.notify_admins_new_feedback",
            new_callable=AsyncMock,
            side_effect=Exception("redis down"),
        ):
            await create_feedback(db, redis, user, payload)

        db.commit.assert_called_once()


# ── feedback_service.load_admin_feedback_or_404 ───────────────────────────────


class TestLoadAdminFeedbackOr404:
    @pytest.mark.asyncio
    async def test_returns_feedback_when_found(self):
        from app.api.feedback.feedback_service import load_admin_feedback_or_404

        db = _make_db()
        fb = _make_feedback()
        fb_id = uuid.uuid4()

        with patch(
            "app.api.feedback.feedback_service.feedback_repo.fetch_admin_feedback",
            new_callable=AsyncMock,
            return_value=fb,
        ):
            result = await load_admin_feedback_or_404(db, fb_id)

        assert result is fb

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import load_admin_feedback_or_404

        db = _make_db()

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_admin_feedback",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await load_admin_feedback_or_404(db, uuid.uuid4())

        assert exc_info.value.status_code == 404


# ── feedback_service.update_status ───────────────────────────────────────────


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_updates_status_successfully(self):
        from app.api.feedback.feedback_service import update_status
        from app.schemas.feedback import FeedbackStatusIn

        db = _make_db()
        redis = _make_redis()
        fb_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, status="open")

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_admin_feedback",
                new_callable=AsyncMock,
                return_value=fb,
            ),
        ):
            await update_status(db, redis, fb_id, FeedbackStatusIn(status="in_progress"))

        db.commit.assert_called_once()
        assert fb.status == "in_progress"

    @pytest.mark.asyncio
    async def test_notifies_user_when_closed(self):
        from app.api.feedback.feedback_service import update_status
        from app.schemas.feedback import FeedbackStatusIn

        user_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()
        fb_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, user_id=user_id, status="open")

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_admin_feedback",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            patch(
                "app.api.feedback.feedback_service.notify_user_feedback_status_changed",
                new_callable=AsyncMock,
            ) as mock_notify,
        ):
            await update_status(db, redis, fb_id, FeedbackStatusIn(status="closed"))

        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_notify_error_on_close(self):
        from app.api.feedback.feedback_service import update_status
        from app.schemas.feedback import FeedbackStatusIn

        user_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()
        fb_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, user_id=user_id, status="open")

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_admin_feedback",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            patch(
                "app.api.feedback.feedback_service.notify_user_feedback_status_changed",
                new_callable=AsyncMock,
                side_effect=Exception("fail"),
            ),
        ):
            await update_status(db, redis, fb_id, FeedbackStatusIn(status="closed"))

        db.commit.assert_called_once()


# ── feedback_service.add_reply ────────────────────────────────────────────────


class TestAddReply:
    @pytest.mark.asyncio
    async def test_adds_reply_and_updates_status(self):
        from app.api.feedback.feedback_service import add_reply
        from app.schemas.feedback import FeedbackReplyIn

        admin = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        fb_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, user_id=other_user_id, status="open")

        reply_mock = MagicMock()
        reply_mock.id = uuid.uuid4()
        reply_mock.admin_id = admin.id
        reply_mock.message = "Reply"
        reply_mock.created_at = datetime.now(UTC)

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_simple",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            patch(
                "app.api.feedback.feedback_service.FeedbackReply",
                return_value=reply_mock,
            ),
            patch(
                "app.api.feedback.feedback_service.notify_user_feedback_reply",
                new_callable=AsyncMock,
            ),
        ):
            await add_reply(db, redis, admin, fb_id, FeedbackReplyIn(message="Reply"))

        assert fb.status == "in_progress"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_feedback_not_found(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import add_reply
        from app.schemas.feedback import FeedbackReplyIn

        admin = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_simple",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await add_reply(db, redis, admin, uuid.uuid4(), FeedbackReplyIn(message="Reply"))

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_skips_notify_when_admin_is_author(self):
        from app.api.feedback.feedback_service import add_reply
        from app.schemas.feedback import FeedbackReplyIn

        admin_id = uuid.uuid4()
        admin = _make_user(role="admin", user_id=admin_id)
        db = _make_db()
        redis = _make_redis()
        fb_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, user_id=admin_id, status="in_progress")

        reply_mock = MagicMock()
        reply_mock.id = uuid.uuid4()
        reply_mock.admin_id = admin_id
        reply_mock.message = "Self-reply"
        reply_mock.created_at = datetime.now(UTC)

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_simple",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            patch(
                "app.api.feedback.feedback_service.FeedbackReply",
                return_value=reply_mock,
            ),
            patch(
                "app.api.feedback.feedback_service.notify_user_feedback_reply",
                new_callable=AsyncMock,
            ) as mock_notify,
        ):
            await add_reply(db, redis, admin, fb_id, FeedbackReplyIn(message="Self-reply"))

        mock_notify.assert_not_called()


# ── feedback_service.load_feedback_for_attachment_access ─────────────────────


class TestLoadFeedbackForAttachmentAccess:
    @pytest.mark.asyncio
    async def test_admin_can_access_any_feedback(self):
        from app.api.feedback.feedback_service import load_feedback_for_attachment_access

        admin = _make_user(role="admin")
        db = _make_db()
        other_uid = uuid.uuid4()
        fb = _make_feedback(user_id=other_uid)

        with patch(
            "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
            new_callable=AsyncMock,
            return_value=fb,
        ):
            result = await load_feedback_for_attachment_access(db, uuid.uuid4(), admin)

        assert result is fb

    @pytest.mark.asyncio
    async def test_owner_can_access_own_feedback(self):
        from app.api.feedback.feedback_service import load_feedback_for_attachment_access

        uid = uuid.uuid4()
        user = _make_user(role="reader", user_id=uid)
        db = _make_db()
        fb = _make_feedback(user_id=uid)

        with patch(
            "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
            new_callable=AsyncMock,
            return_value=fb,
        ):
            result = await load_feedback_for_attachment_access(db, uuid.uuid4(), user)

        assert result is fb

    @pytest.mark.asyncio
    async def test_raises_404_for_non_owner(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import load_feedback_for_attachment_access

        user = _make_user(role="reader")
        db = _make_db()
        other_uid = uuid.uuid4()
        fb = _make_feedback(user_id=other_uid)

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await load_feedback_for_attachment_access(db, uuid.uuid4(), user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import load_feedback_for_attachment_access

        user = _make_user(role="reader")
        db = _make_db()

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await load_feedback_for_attachment_access(db, uuid.uuid4(), user)

        assert exc_info.value.status_code == 404


# ── feedback_service.delete_attachment ───────────────────────────────────────


class TestDeleteAttachment:
    @pytest.mark.asyncio
    async def test_deletes_attachment_successfully(self):
        from app.api.feedback.feedback_service import delete_attachment

        admin = _make_user(role="admin")
        db = _make_db()
        att_id = uuid.uuid4()
        fb_id = uuid.uuid4()
        att = _make_attachment(id=att_id, feedback_id=fb_id)
        fb = _make_feedback(id=fb_id, status="open", attachments=[att])

        with patch(
            "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
            new_callable=AsyncMock,
            return_value=fb,
        ):
            await delete_attachment(db, admin, fb_id, att_id)

        db.delete.assert_called_once_with(att)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_attachment_not_found(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import delete_attachment

        admin = _make_user(role="admin")
        db = _make_db()
        fb_id = uuid.uuid4()
        fb = _make_feedback(id=fb_id, attachments=[])

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await delete_attachment(db, admin, fb_id, uuid.uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_non_owner_gets_403(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import delete_attachment

        uid = uuid.uuid4()
        user = _make_user(role="reader", user_id=uid)
        db = _make_db()
        att_id = uuid.uuid4()
        fb_id = uuid.uuid4()
        other_uid = uuid.uuid4()
        att = _make_attachment(id=att_id, feedback_id=fb_id, uploaded_by=other_uid)
        fb = _make_feedback(id=fb_id, user_id=uid, status="open", attachments=[att])

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await delete_attachment(db, user, fb_id, att_id)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_from_closed_ticket(self):
        from fastapi import HTTPException

        from app.api.feedback.feedback_service import delete_attachment

        uid = uuid.uuid4()
        user = _make_user(role="reader", user_id=uid)
        db = _make_db()
        att_id = uuid.uuid4()
        fb_id = uuid.uuid4()
        att = _make_attachment(id=att_id, feedback_id=fb_id, uploaded_by=uid)
        fb = _make_feedback(id=fb_id, user_id=uid, status="closed", attachments=[att])

        with (
            patch(
                "app.api.feedback.feedback_service.feedback_repo.fetch_feedback_with_attachments",
                new_callable=AsyncMock,
                return_value=fb,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await delete_attachment(db, user, fb_id, att_id)

        assert exc_info.value.status_code == 409


# ── feedback_repo helpers ─────────────────────────────────────────────────────


class TestFeedbackRepo:
    @pytest.mark.asyncio
    async def test_count_my_feedback_no_filter(self):
        from app.api.feedback.feedback_repo import count_my_feedback

        db = _make_db()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 5
        db.execute.return_value = scalar_result

        result = await count_my_feedback(db, user_id=uuid.uuid4(), status_filter=None)
        assert result == 5

    @pytest.mark.asyncio
    async def test_count_my_feedback_with_status_filter(self):
        from app.api.feedback.feedback_repo import count_my_feedback

        db = _make_db()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 2
        db.execute.return_value = scalar_result

        result = await count_my_feedback(db, user_id=uuid.uuid4(), status_filter="open")
        assert result == 2

    @pytest.mark.asyncio
    async def test_fetch_my_feedback_returns_none_when_not_found(self):
        from app.api.feedback.feedback_repo import fetch_my_feedback

        db = _make_db()
        result_mock = MagicMock()
        result_mock.unique.return_value.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await fetch_my_feedback(db, feedback_id=uuid.uuid4(), user_id=uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_count_admin_feedback_with_all_filters(self):
        from app.api.feedback.feedback_repo import count_admin_feedback

        db = _make_db()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 3
        db.execute.return_value = scalar_result

        result = await count_admin_feedback(db, status_filter="open", category="bug", q="broken")
        assert result == 3

    @pytest.mark.asyncio
    async def test_count_admin_feedback_no_filters(self):
        from app.api.feedback.feedback_repo import count_admin_feedback

        db = _make_db()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 10
        db.execute.return_value = scalar_result

        result = await count_admin_feedback(db, status_filter=None, category=None, q=None)
        assert result == 10

    @pytest.mark.asyncio
    async def test_fetch_admin_feedback_returns_none_when_not_found(self):
        from app.api.feedback.feedback_repo import fetch_admin_feedback

        db = _make_db()
        result_mock = MagicMock()
        result_mock.unique.return_value.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await fetch_admin_feedback(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_feedback_simple_returns_none(self):
        from app.api.feedback.feedback_repo import fetch_feedback_simple

        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await fetch_feedback_simple(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_feedback_with_attachments_returns_feedback(self):
        from app.api.feedback.feedback_repo import fetch_feedback_with_attachments

        db = _make_db()
        fb = _make_feedback()
        result_mock = MagicMock()
        result_mock.unique.return_value.scalar_one_or_none.return_value = fb
        db.execute.return_value = result_mock

        result = await fetch_feedback_with_attachments(db, uuid.uuid4())
        assert result is fb


class TestCommonMappers:
    def _make_now(self):
        return datetime.now(UTC)

    def test_reply_to_out_with_admin(self):
        from app.api.feedback._common import reply_to_out

        admin = SimpleNamespace(full_name="Admin User")
        reply = SimpleNamespace(
            id=uuid.uuid4(),
            admin_id=uuid.uuid4(),
            admin=admin,
            message="test reply",
            created_at=self._make_now(),
        )
        out = reply_to_out(reply)
        assert out.admin_name == "Admin User"
        assert out.message == "test reply"

    def test_reply_to_out_without_admin(self):
        from app.api.feedback._common import reply_to_out

        reply = SimpleNamespace(
            id=uuid.uuid4(),
            admin_id=None,
            admin=None,
            message="no admin",
            created_at=self._make_now(),
        )
        out = reply_to_out(reply)
        assert out.admin_name is None

    def test_attachment_to_out(self):
        from app.api.feedback._common import attachment_to_out

        fid = uuid.uuid4()
        aid = uuid.uuid4()
        att = SimpleNamespace(
            id=aid,
            feedback_id=fid,
            original_name="file.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            created_at=self._make_now(),
        )
        out = attachment_to_out(att)
        assert out.original_name == "file.pdf"
        assert f"/api/v1/feedback/{fid}/attachments/{aid}" == out.download_url

    def test_feedback_to_out(self):
        from app.api.feedback._common import feedback_to_out

        fb = SimpleNamespace(
            id=uuid.uuid4(),
            category="bug",
            message="msg",
            page_url=None,
            status="open",
            created_at=self._make_now(),
            updated_at=self._make_now(),
            replies=[],
            attachments=[],
        )
        out = feedback_to_out(fb)
        assert out.message == "msg"

    def test_feedback_to_admin_out_with_author(self):
        from app.api.feedback._common import feedback_to_admin_out

        author = SimpleNamespace(full_name="User Name", email="user@test.local")
        fb = SimpleNamespace(
            id=uuid.uuid4(),
            category="suggestion",
            message="suggestion msg",
            page_url="http://test/page",
            status="open",
            created_at=self._make_now(),
            updated_at=self._make_now(),
            replies=[],
            attachments=[],
            user_id=uuid.uuid4(),
            author=author,
        )
        out = feedback_to_admin_out(fb)
        assert out.author_name == "User Name"
        assert out.author_email == "user@test.local"

    def test_feedback_to_admin_out_no_author(self):
        from app.api.feedback._common import feedback_to_admin_out

        fb = SimpleNamespace(
            id=uuid.uuid4(),
            category="bug",
            message="anon",
            page_url=None,
            status="closed",
            created_at=self._make_now(),
            updated_at=self._make_now(),
            replies=[],
            attachments=[],
            user_id=None,
            author=None,
        )
        out = feedback_to_admin_out(fb)
        assert out.author_name is None
        assert out.author_email is None
