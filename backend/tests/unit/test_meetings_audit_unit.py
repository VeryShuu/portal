from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.meetings import audit


def _session_cm(audit_db):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=audit_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _audit_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _request(headers):
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host="10.0.0.9"),
    )


class TestPushMeetingsAudit:
    async def test_writes_row_with_forwarded_ip_and_user_metadata(self):
        audit_db = _audit_db()
        user = SimpleNamespace(
            id=uuid.uuid4(), email="u@portal.local", role="admin", full_name="Jane"
        )
        request = _request(
            {"X-Forwarded-For": "203.0.113.5, 10.0.0.1", "User-Agent": "pytest"}
        )

        with patch.object(audit, "AsyncSessionLocal", return_value=_session_cm(audit_db)):
            await audit.push_meetings_audit(
                action=audit.ROOM_CREATED,
                user=user,
                request=request,
                resource_type="room",
                resource_id=uuid.uuid4(),
                resource_title="Room A",
                details={"extra": "x"},
            )

        audit_db.execute.assert_awaited_once()
        audit_db.commit.assert_awaited_once()
        params = audit_db.execute.await_args.args[1]
        assert params["ip_address"] == "203.0.113.5"
        assert params["user_agent"] == "pytest"
        assert '"user_role": "admin"' in params["metadata"]
        assert '"username": "Jane"' in params["metadata"]
        assert '"extra": "x"' in params["metadata"]

    async def test_falls_back_to_client_host_when_no_forwarded_header(self):
        audit_db = _audit_db()
        request = _request({"User-Agent": "ua"})

        with patch.object(audit, "AsyncSessionLocal", return_value=_session_cm(audit_db)):
            await audit.push_meetings_audit(
                action=audit.ROOM_UPDATED, user=None, request=request
            )

        params = audit_db.execute.await_args.args[1]
        assert params["ip_address"] == "10.0.0.9"
        assert params["user_id"] is None
        assert params["user_email"] is None

    async def test_no_request_no_user(self):
        audit_db = _audit_db()

        with patch.object(audit, "AsyncSessionLocal", return_value=_session_cm(audit_db)):
            await audit.push_meetings_audit(
                action=audit.MEETING_DELETED, user=None, request=None
            )

        params = audit_db.execute.await_args.args[1]
        assert params["ip_address"] is None
        assert params["user_agent"] is None
        assert params["metadata"] == "{}"

    async def test_db_failure_is_swallowed_and_logged(self):
        audit_db = _audit_db()
        audit_db.execute = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch.object(audit, "AsyncSessionLocal", return_value=_session_cm(audit_db)),
            patch.object(audit.logger, "warning") as warn,
        ):
            # Must not raise despite the DB error.
            await audit.push_meetings_audit(
                action=audit.SERIES_DELETED, user=None, request=None
            )

        warn.assert_called_once()
        assert warn.call_args.args[0] == "meetings.audit.log_failed"
