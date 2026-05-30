from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _make_session():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = uuid.uuid4()
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    return session


class TestEnqueueOutboxEmail:
    async def test_returns_uuid(self):
        from app.services.email_outbox import enqueue_outbox_email

        session = _make_session()
        result_id = await enqueue_outbox_email(
            session,
            kind="generic",
            to_email="user@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
        )
        assert isinstance(result_id, uuid.UUID)

    async def test_with_all_params(self):
        from app.services.email_outbox import enqueue_outbox_email

        session = _make_session()
        uid = uuid.uuid4()
        rid = uuid.uuid4()
        new_id = await enqueue_outbox_email(
            session,
            kind="meeting",
            to_email="user@example.com",
            subject="Meeting invite",
            body_html="<p>Join us</p>",
            body_text="Join us",
            payload={"key": "value"},
            related_resource_type="meeting_booking",
            related_resource_id=rid,
            created_by_user_id=uid,
            max_attempts=3,
        )
        assert isinstance(new_id, uuid.UUID)
        session.execute.assert_awaited_once()

    async def test_empty_payload_default(self):
        from app.services.email_outbox import enqueue_outbox_email

        session = _make_session()
        await enqueue_outbox_email(
            session,
            kind="generic",
            to_email="x@y.com",
            subject="S",
        )
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["payload"] == "{}"

    async def test_with_none_payload(self):
        from app.services.email_outbox import enqueue_outbox_email

        session = _make_session()
        await enqueue_outbox_email(
            session,
            kind="generic",
            to_email="x@y.com",
            subject="S",
            payload=None,
        )
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["payload"] == "{}"


class TestClaimPending:
    async def test_returns_list_of_dicts(self):
        from app.services.email_outbox import claim_pending

        row1 = {
            "id": uuid.uuid4(),
            "kind": "generic",
            "to_email": "a@b.com",
            "subject": "S",
            "body_html": "",
            "body_text": None,
            "payload": {},
            "attempts": 0,
            "max_attempts": 3,
        }
        row2 = {
            "id": uuid.uuid4(),
            "kind": "meeting",
            "to_email": "c@d.com",
            "subject": "M",
            "body_html": "",
            "body_text": None,
            "payload": {},
            "attempts": 1,
            "max_attempts": 3,
        }

        mappings_result = MagicMock()
        mappings_result.all.return_value = [row1, row2]
        execute_result = MagicMock()
        execute_result.mappings.return_value = mappings_result

        session = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result)

        rows = await claim_pending(session, limit=10)
        assert len(rows) == 2
        assert all(isinstance(r, dict) for r in rows)

    async def test_empty_result(self):
        from app.services.email_outbox import claim_pending

        mappings_result = MagicMock()
        mappings_result.all.return_value = []
        execute_result = MagicMock()
        execute_result.mappings.return_value = mappings_result

        session = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result)

        rows = await claim_pending(session)
        assert rows == []


class TestMarkSent:
    async def test_executes_update(self):
        from app.services.email_outbox import mark_sent

        session = AsyncMock()
        outbox_id = uuid.uuid4()
        await mark_sent(session, outbox_id)
        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert params["id"] == outbox_id


class TestMarkFailed:
    async def test_permanent_error_class_gives_dlq(self):
        from app.services.email_outbox import STATUS_DLQ, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="SomeError",
            error_class="permanent",
            current_attempts=0,
            max_attempts=3,
        )
        assert new_status == STATUS_DLQ

    async def test_exhausted_attempts_gives_dlq(self):
        from app.services.email_outbox import STATUS_DLQ, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="SomeError",
            error_class="transient",
            current_attempts=2,
            max_attempts=3,
        )
        assert new_status == STATUS_DLQ

    async def test_retryable_gives_pending(self):
        from app.services.email_outbox import STATUS_PENDING, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="TimeoutError",
            error_class="transient",
            current_attempts=0,
            max_attempts=5,
        )
        assert new_status == STATUS_PENDING

    async def test_executes_update_with_defer_when_pending(self):
        from app.services.email_outbox import mark_failed

        session = AsyncMock()
        await mark_failed(
            session,
            uuid.uuid4(),
            error="timeout",
            error_type="TimeoutError",
            error_class="transient",
            current_attempts=1,
            max_attempts=10,
        )
        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert "defer" in params

    async def test_executes_without_defer_when_dlq(self):
        from app.services.email_outbox import mark_failed

        session = AsyncMock()
        await mark_failed(
            session,
            uuid.uuid4(),
            error="auth fail",
            error_type="SMTPAuthError",
            error_class="permanent",
            current_attempts=0,
            max_attempts=5,
        )
        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert "defer" not in params

    async def test_error_truncated_to_4000_chars(self):
        from app.services.email_outbox import mark_failed

        session = AsyncMock()
        long_error = "x" * 5000
        await mark_failed(
            session,
            uuid.uuid4(),
            error=long_error,
            error_type="E",
            error_class="permanent",
            current_attempts=0,
            max_attempts=1,
        )
        params = session.execute.call_args[0][1]
        assert len(params["error"]) == 4000


class TestRescheduleForRetry:
    async def test_returns_true_when_updated(self):
        from app.services.email_outbox import reschedule_for_retry

        result = MagicMock()
        result.rowcount = 1
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        ok = await reschedule_for_retry(session, uuid.uuid4())
        assert ok is True

    async def test_returns_false_when_not_updated(self):
        from app.services.email_outbox import reschedule_for_retry

        result = MagicMock()
        result.rowcount = 0
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        ok = await reschedule_for_retry(session, uuid.uuid4())
        assert ok is False

    async def test_reset_attempts_param_passed(self):
        from app.services.email_outbox import reschedule_for_retry

        result = MagicMock()
        result.rowcount = 1
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        await reschedule_for_retry(session, uuid.uuid4(), reset_attempts=True)
        params = session.execute.call_args[0][1]
        assert params["reset"] is True


class TestCancel:
    async def test_returns_true_when_cancelled(self):
        from app.services.email_outbox import cancel

        result = MagicMock()
        result.rowcount = 1
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        ok = await cancel(session, uuid.uuid4())
        assert ok is True

    async def test_returns_false_when_not_found(self):
        from app.services.email_outbox import cancel

        result = MagicMock()
        result.rowcount = 0
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        ok = await cancel(session, uuid.uuid4())
        assert ok is False


class TestCleanupOldSent:
    async def test_returns_deleted_count(self):
        from app.services.email_outbox import cleanup_old_sent

        result = MagicMock()
        result.rowcount = 42
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        count = await cleanup_old_sent(session, older_than_days=30)
        assert count == 42

    async def test_default_30_days(self):
        from app.services.email_outbox import cleanup_old_sent

        result = MagicMock()
        result.rowcount = 0
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        await cleanup_old_sent(session)
        session.execute.assert_awaited_once()


class TestEncodeDecodeIcal:
    def test_roundtrip(self):
        from app.services.email_outbox import decode_ical_bytes, encode_ical_bytes

        data = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        encoded = encode_ical_bytes(data)
        assert isinstance(encoded, str)
        decoded = decode_ical_bytes(encoded)
        assert decoded == data

    def test_encode_returns_ascii(self):
        from app.services.email_outbox import encode_ical_bytes

        result = encode_ical_bytes(b"\x00\xff\xfe")
        assert result.isascii()


class TestJsonDumps:
    def test_simple_dict(self):
        from app.services.email_outbox import _json_dumps

        result = _json_dumps({"key": "value"})
        assert '"key"' in result
        assert '"value"' in result

    def test_non_serializable_uses_str(self):
        import uuid as _uuid

        from app.services.email_outbox import _json_dumps

        uid = _uuid.uuid4()
        result = _json_dumps({"id": uid})
        assert str(uid) in result
