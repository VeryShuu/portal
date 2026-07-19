"""Unit-тесты для app.services.messenger_outbox.

Полный аналог ``test_email_outbox_service.py``: enqueue/claim/mark_sent/
mark_failed/requeue/reschedule/cancel/cleanup через замоканную SQLAlchemy-
сессию. Покрывает:
- enqueue: возвращает UUID, payload по умолчанию ``{}`` (JSONB), проброс
  related_resource_id/created_by_user_id.
- claim_pending: возвращает list[dict], пустой → [].
- mark_sent: выполняет UPDATE.
- mark_failed: permanent → DLQ, exhausted → DLQ, transient → PENDING+defer.
- requeue_stale_sending: возвращает rowcount, не падает.
- reschedule_for_retry / cancel / cleanup_old_sent.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock


def _make_session():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = uuid.uuid4()
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    return session


class TestEnqueue:
    async def test_returns_uuid(self):
        from app.services.messenger_outbox import enqueue_messenger_message

        session = _make_session()
        result_id = await enqueue_messenger_message(
            session,
            provider="max",
            chat_id="100",
            text="hi",
        )
        assert isinstance(result_id, uuid.UUID)

    async def test_with_all_params(self):
        from app.services.messenger_outbox import enqueue_messenger_message

        session = _make_session()
        uid = uuid.uuid4()
        rid = uuid.uuid4()
        new_id = await enqueue_messenger_message(
            session,
            provider="max",
            chat_id="100",
            text="hello",
            payload={"attachments": [{"type": "inline_keyboard"}]},
            related_resource_type="helpdesk_ticket",
            related_resource_id=rid,
            created_by_user_id=uid,
            max_attempts=3,
        )
        assert isinstance(new_id, uuid.UUID)
        session.execute.assert_awaited_once()

    async def test_empty_payload_default(self):
        from app.services.messenger_outbox import enqueue_messenger_message

        session = _make_session()
        await enqueue_messenger_message(
            session,
            provider="max",
            chat_id="1",
            text="x",
        )
        params = session.execute.call_args[0][1]
        assert params["payload"] == "{}"

    async def test_none_payload_default(self):
        from app.services.messenger_outbox import enqueue_messenger_message

        session = _make_session()
        await enqueue_messenger_message(
            session,
            provider="max",
            chat_id="1",
            text="x",
            payload=None,
        )
        params = session.execute.call_args[0][1]
        assert params["payload"] == "{}"


class TestClaimPending:
    async def test_returns_list_of_dicts(self):
        from app.services.messenger_outbox import claim_pending

        row1 = {
            "id": uuid.uuid4(),
            "provider": "max",
            "chat_id": "100",
            "text": "msg1",
            "payload": {"format": "markdown"},
            "attempts": 0,
            "max_attempts": 6,
        }
        row2 = {
            "id": uuid.uuid4(),
            "provider": "max",
            "chat_id": "100",
            "text": "msg2",
            "payload": {},
            "attempts": 1,
            "max_attempts": 6,
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
        from app.services.messenger_outbox import claim_pending

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
        from app.services.messenger_outbox import mark_sent

        session = AsyncMock()
        outbox_id = uuid.uuid4()
        await mark_sent(session, outbox_id)
        session.execute.assert_awaited_once()
        params = session.execute.call_args[0][1]
        assert params["id"] == outbox_id


class TestMarkFailed:
    async def test_permanent_error_class_gives_dlq(self):
        from app.services.messenger_outbox import STATUS_DLQ, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="MaxApiError",
            error_class="permanent",
            current_attempts=0,
            max_attempts=6,
        )
        assert new_status == STATUS_DLQ

    async def test_exhausted_attempts_give_dlq(self):
        from app.services.messenger_outbox import STATUS_DLQ, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="TimeoutError",
            error_class="transient",
            current_attempts=5,
            max_attempts=6,
        )
        assert new_status == STATUS_DLQ

    async def test_retryable_gives_pending(self):
        from app.services.messenger_outbox import STATUS_PENDING, mark_failed

        session = AsyncMock()
        new_status = await mark_failed(
            session,
            uuid.uuid4(),
            error="err",
            error_type="TimeoutError",
            error_class="transient",
            current_attempts=0,
            max_attempts=6,
        )
        assert new_status == STATUS_PENDING


class TestRequeueStaleSending:
    async def test_returns_rowcount(self):
        from app.services.messenger_outbox import requeue_stale_sending

        session = AsyncMock()
        result = MagicMock(rowcount=2)
        session.execute = AsyncMock(return_value=result)

        count = await requeue_stale_sending(session, older_than_seconds=600)
        assert count == 2

    async def test_zero_rowcount(self):
        from app.services.messenger_outbox import requeue_stale_sending

        session = AsyncMock()
        result = MagicMock(rowcount=0)
        session.execute = AsyncMock(return_value=result)

        count = await requeue_stale_sending(session)
        assert count == 0


class TestRescheduleAndCancel:
    async def test_reschedule_returns_true_when_updated(self):
        from app.services.messenger_outbox import reschedule_for_retry

        session = AsyncMock()
        result = MagicMock(rowcount=1)
        session.execute = AsyncMock(return_value=result)

        ok = await reschedule_for_retry(session, uuid.uuid4())
        assert ok is True

    async def test_reschedule_returns_false_when_not_found(self):
        from app.services.messenger_outbox import reschedule_for_retry

        session = AsyncMock()
        result = MagicMock(rowcount=0)
        session.execute = AsyncMock(return_value=result)

        ok = await reschedule_for_retry(session, uuid.uuid4())
        assert ok is False

    async def test_cancel_returns_true_when_updated(self):
        from app.services.messenger_outbox import cancel

        session = AsyncMock()
        result = MagicMock(rowcount=1)
        session.execute = AsyncMock(return_value=result)

        ok = await cancel(session, uuid.uuid4())
        assert ok is True


class TestCleanupOldSent:
    async def test_returns_count(self):
        from app.services.messenger_outbox import cleanup_old_sent

        session = AsyncMock()
        result = MagicMock(rowcount=5)
        session.execute = AsyncMock(return_value=result)

        count = await cleanup_old_sent(session, older_than_days=30)
        assert count == 5
