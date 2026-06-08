"""TST-02: send_meeting_email worker task must complete without TypeError (BLK-02).

`push_meetings_audit` is keyword-only and opens its own session; calling it
with a positional `db` argument was the original bug. This test ensures the
worker task runs end-to-end with mocked SMTP + audit and writes an EMAIL_SENT
audit entry.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from arq import Retry

pytestmark = pytest.mark.asyncio

_SMTP_CFG = {
    "from_address": "noreply@portal.local",
    "host": "smtp",
    "port": 25,
    "username": "",
    "password": "",
    "use_tls": False,
    "use_starttls": False,
}


def _make_modules(enabled: bool = True):
    return type("M", (), {"meetings": type("Mt", (), {"enabled": enabled})()})()


@contextmanager
def _patched(*, smtp_send, modules, fake_audit, classify=None, defer=None):
    patches = [
        patch(
            "app.worker.tasks.meetings.email.load_smtp_config",
            return_value=_SMTP_CFG,
        ),
        patch("app.worker.tasks.meetings.email.smtp_send", new=smtp_send),
        patch("app.core.modules_config.load_modules", return_value=modules),
        patch("app.services.meetings.audit.push_meetings_audit", new=fake_audit),
    ]
    if classify is not None:
        patches.append(
            patch("app.worker.tasks.meetings.email.classify_smtp_error", return_value=classify)
        )
    if defer is not None:
        patches.append(
            patch("app.worker.tasks.meetings.email.compute_retry_defer", return_value=defer)
        )
    import contextlib

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


async def _send(ctx: dict | None = None) -> None:
    from app.worker.tasks.meetings.email import send_meeting_email

    await send_meeting_email(
        ctx or {"job_try": 1},
        to_email="alice@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        ical_bytes=b"BEGIN:VCALENDAR\nEND:VCALENDAR",
        method="REQUEST",
    )


async def test_send_meeting_email_writes_audit_without_typeerror() -> None:
    from app.worker.tasks.meetings.email import send_meeting_email

    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    fake_modules = type("M", (), {"meetings": type("Mt", (), {"enabled": True})()})()

    with (
        patch(
            "app.worker.tasks.meetings.email.load_smtp_config",
            return_value={
                "from_address": "noreply@portal.local",
                "host": "smtp",
                "port": 25,
                "username": "",
                "password": "",
                "use_tls": False,
                "use_starttls": False,
            },
        ),
        patch(
            "app.worker.tasks.meetings.email.smtp_send",
            new=AsyncMock(return_value=None),
        ),
        patch("app.core.modules_config.load_modules", return_value=fake_modules),
        patch("app.services.meetings.audit.push_meetings_audit", new=fake_audit),
    ):
        await send_meeting_email(
            {"job_try": 1},
            to_email="alice@example.com",
            subject="Hello",
            html_body="<p>Hi</p>",
            ical_bytes=b"BEGIN:VCALENDAR\nEND:VCALENDAR",
            method="REQUEST",
        )

    assert audit_calls, "expected EMAIL_SENT audit entry"
    entry = audit_calls[-1]
    # All callers must use keyword-only signature: no positional db arg.
    assert "db" not in entry
    assert entry.get("action") is not None
    details = entry.get("details") or {}
    assert details.get("to") == "alice@example.com"
    assert details.get("method") == "REQUEST"


async def test_skips_when_meetings_module_disabled() -> None:
    smtp_send = AsyncMock()
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    with _patched(
        smtp_send=smtp_send,
        modules=_make_modules(enabled=False),
        fake_audit=fake_audit,
    ):
        await _send()

    smtp_send.assert_not_awaited()
    assert audit_calls == []


async def test_module_check_failure_does_not_block_send() -> None:
    smtp_send = AsyncMock(return_value=None)
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    with (
        patch("app.worker.tasks.meetings.email.load_smtp_config", return_value=_SMTP_CFG),
        patch("app.worker.tasks.meetings.email.smtp_send", new=smtp_send),
        patch(
            "app.core.modules_config.load_modules",
            side_effect=RuntimeError("config unreadable"),
        ),
        patch("app.services.meetings.audit.push_meetings_audit", new=fake_audit),
    ):
        await _send()

    # module check failed but send proceeded → EMAIL_SENT audit written
    smtp_send.assert_awaited_once()
    assert audit_calls


async def test_permanent_failure_reraises_and_writes_failed_audit() -> None:
    smtp_send = AsyncMock(side_effect=RuntimeError("smtp boom"))
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    with _patched(
        smtp_send=smtp_send,
        modules=_make_modules(True),
        fake_audit=fake_audit,
        classify="permanent",
    ), pytest.raises(RuntimeError, match="smtp boom"):
        await _send({"job_try": 1})

    assert audit_calls, "expected EMAIL_FAILED audit entry"
    details = audit_calls[-1].get("details") or {}
    assert details.get("final") is True
    assert details.get("error_class") == "permanent"


async def test_transient_failure_raises_retry() -> None:
    smtp_send = AsyncMock(side_effect=RuntimeError("temporary"))
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    with _patched(
        smtp_send=smtp_send,
        modules=_make_modules(True),
        fake_audit=fake_audit,
        classify="transient",
        defer=7,
    ), pytest.raises(Retry) as exc_info:
        await _send({"job_try": 1})

    assert exc_info.value.defer_score == 7000  # arq stores defer in milliseconds
    details = audit_calls[-1].get("details") or {}
    assert details.get("final") is False


async def test_transient_failure_final_on_max_tries() -> None:
    from app.worker.tasks.email_utils import MAX_TRIES

    smtp_send = AsyncMock(side_effect=RuntimeError("temporary"))
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs) -> None:
        audit_calls.append(kwargs)

    with _patched(
        smtp_send=smtp_send,
        modules=_make_modules(True),
        fake_audit=fake_audit,
        classify="transient",
    ), pytest.raises(RuntimeError, match="temporary"):
        await _send({"job_try": MAX_TRIES})

    details = audit_calls[-1].get("details") or {}
    assert details.get("final") is True


async def test_audit_write_failure_is_swallowed_on_retry() -> None:
    smtp_send = AsyncMock(side_effect=RuntimeError("temporary"))

    async def boom_audit(**kwargs) -> None:
        raise RuntimeError("audit down")

    # audit failure must not mask the Retry control-flow
    with (
        _patched(
            smtp_send=smtp_send,
            modules=_make_modules(True),
            fake_audit=boom_audit,
            classify="transient",
            defer=3,
        ),
        pytest.raises(Retry),
    ):
        await _send({"job_try": 1})
