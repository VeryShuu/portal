"""Unit-тесты для app.worker.tasks.email_outbox.

Покрывают process_email_outbox / cleanup_email_outbox / _build_mime через
фейковую SQLAlchemy-сессию и stubbed aiosmtplib.send:
- happy path: 2 claimed → отправлены оба → mark_sent ×2 → возвращает 2
- smtp_not_configured: всё в outbox → mark_failed с error_class=transient
- send raises permanent (SMTPAuthenticationError) → mark_failed permanent
- send raises transient (TimeoutError) → mark_failed transient
- claim_pending пусто → ранний выход 0
- внутренняя exception в claim → logger.exception + 0
- cleanup_email_outbox → возвращает delete count
- _build_mime: KIND_MEETING с ical_b64 → multipart/mixed + calendar attachment
- _build_mime: KIND_MEETING без ical_b64 → не падает
- _build_mime: KIND_GENERIC c body_text → alternative с plain+html
- _build_mime: KIND_GENERIC без body_text → только html
- _build_mime: пустой from_address → дефолтный portal@company.local
"""

from __future__ import annotations

import base64
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── helpers ──────────────────────────────────────────────────────────────


class _FakeSession:
    """Поддерживает `async with session:` + `async with session.begin():`."""

    def __init__(self):
        self.entered = 0
        self.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *_):
        return False

    @asynccontextmanager
    async def begin(self):
        yield self


class _FakeRedis:
    """Fake redis для distributed lock в process_email_outbox (audit [L4]).

    По образцу tests/unit/test_worker_messenger_outbox.py::_FakeRedis:
    set(nx=True) → lock_acquired; eval (Lua-release) → no-op.
    """

    def __init__(self, *, lock_acquired: bool = True):
        self._lock_acquired = lock_acquired
        self.set = AsyncMock(return_value=lock_acquired)
        self.eval = AsyncMock(return_value=1)


@asynccontextmanager
async def _session_cm(sess):
    yield sess


def _patch_session_local(monkeypatch, sess):
    """Подменяет AsyncSessionLocal так, чтобы `async with AsyncSessionLocal() as s` → sess."""
    from app.worker.tasks import email_outbox as eo

    monkeypatch.setattr(eo, "AsyncSessionLocal", lambda: sess)


def _mk_row(
    *,
    kind="generic",
    attempts=0,
    max_attempts=6,
    ical_b64=None,
    body_html="<p>hi</p>",
    body_text=None,
    to_email="to@x.com",
    subject="Subj",
    inline_images=None,
):
    payload = {}
    if ical_b64 is not None:
        payload["ical_b64"] = ical_b64
        payload["method"] = "REQUEST"
    if inline_images is not None:
        payload["inline_images"] = inline_images
    return {
        "id": uuid.uuid4(),
        "kind": kind,
        "to_email": to_email,
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
        "payload": payload,
        "attempts": attempts,
        "max_attempts": max_attempts,
    }


# ── process_email_outbox ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestProcessEmailOutbox:
    async def test_no_redis_in_context_returns_zero(self):
        """audit [L4]: без redis в ctx distributed lock невозможен — ранний выход."""
        from app.worker.tasks import email_outbox as eo

        result = await eo.process_email_outbox({})
        assert result == 0

    async def test_lock_already_acquired_returns_zero(self, monkeypatch):
        """audit [L4]: если лок занят другим воркером — пропускаем tick."""
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        claim_mock = AsyncMock(return_value=[])
        monkeypatch.setattr(eo, "claim_pending", claim_mock)

        redis = _FakeRedis(lock_acquired=False)
        result = await eo.process_email_outbox({"redis": redis})
        assert result == 0
        # claim не должен вызываться — вышли раньше.
        claim_mock.assert_not_called()

    async def test_no_claimed_returns_zero(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        claim_mock = AsyncMock(return_value=[])
        monkeypatch.setattr(eo, "claim_pending", claim_mock)

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0
        claim_mock.assert_awaited_once()

    async def test_smtp_not_configured_marks_failed(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(eo, "load_smtp_config", lambda: {"host": ""})
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_failed", mark_failed_mock)
        send_mock = AsyncMock()
        monkeypatch.setattr(eo, "smtp_send", send_mock)

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0
        assert mark_failed_mock.await_count == 2
        # Не пытались отправлять.
        send_mock.assert_not_called()
        # transient — для попыток retry.
        kwargs = mark_failed_mock.await_args_list[0].kwargs
        assert kwargs["error_class"] == "transient"
        assert kwargs["error_type"] == "ConfigurationError"

    async def test_send_success_marks_sent(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            eo,
            "load_smtp_config",
            lambda: {"host": "smtp.example", "from_address": "noreply@x.com"},
        )
        monkeypatch.setattr(eo, "smtp_send", AsyncMock())
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_sent", mark_sent_mock)
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_failed", mark_failed_mock)

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 2
        assert mark_sent_mock.await_count == 2
        mark_failed_mock.assert_not_called()

    async def test_send_permanent_error_marks_failed(self, monkeypatch):
        import aiosmtplib

        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            eo,
            "load_smtp_config",
            lambda: {"host": "smtp.example", "from_address": ""},
        )

        exc = aiosmtplib.SMTPAuthenticationError(535, "bad creds")
        monkeypatch.setattr(eo, "smtp_send", AsyncMock(side_effect=exc))
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_failed", mark_failed_mock)
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_sent", mark_sent_mock)

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0
        mark_sent_mock.assert_not_called()
        mark_failed_mock.assert_awaited_once()
        kwargs = mark_failed_mock.await_args.kwargs
        assert kwargs["error_class"] == "permanent"
        assert kwargs["error_type"] == "SMTPAuthenticationError"

    async def test_send_transient_error_marks_failed(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            eo,
            "load_smtp_config",
            lambda: {"host": "smtp.example", "from_address": ""},
        )
        monkeypatch.setattr(eo, "smtp_send", AsyncMock(side_effect=TimeoutError("net")))
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(eo, "mark_failed", mark_failed_mock)

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "transient"

    async def test_requeues_stale_sending_before_claim(self, monkeypatch):
        """E1: перед захватом PENDING воркер возвращает зависшие SENDING в очередь."""
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        requeue_mock = AsyncMock(return_value=0)
        monkeypatch.setattr(eo, "requeue_stale_sending", requeue_mock)
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(return_value=[]))

        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0
        requeue_mock.assert_awaited_once()
        assert (
            requeue_mock.await_args.kwargs["older_than_seconds"] == eo.STALE_SENDING_TIMEOUT_SECONDS
        )

    async def test_outer_exception_is_swallowed(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        monkeypatch.setattr(eo, "claim_pending", AsyncMock(side_effect=RuntimeError("boom")))

        # Не должен пробросить — outer try/except.
        result = await eo.process_email_outbox({"redis": _FakeRedis()})
        assert result == 0


@pytest.mark.asyncio
class TestCleanupEmailOutbox:
    async def test_cleanup_returns_deleted_count(self, monkeypatch):
        from app.worker.tasks import email_outbox as eo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        monkeypatch.setattr(eo, "cleanup_old_sent", AsyncMock(return_value=42))

        result = await eo.cleanup_email_outbox({})
        assert result == 42


# ── _build_mime ──────────────────────────────────────────────────────────


class TestBuildMime:
    def test_meeting_with_ical(self):
        from app.worker.tasks import email_outbox as eo

        ical = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        row = _mk_row(
            kind=eo.KIND_MEETING,
            ical_b64=base64.b64encode(ical).decode("ascii"),
        )
        cfg = {"from_address": "noreply@x.com"}
        msg = eo._build_mime(row, cfg)
        assert msg["Subject"] == "Subj"
        assert msg["From"] == "noreply@x.com"
        assert msg["To"] == "to@x.com"
        assert msg.get_content_type() == "multipart/mixed"
        # Inner alternative contains html + calendar
        parts = msg.get_payload()
        assert len(parts) == 1
        alt = parts[0]
        assert alt.get_content_type() == "multipart/alternative"
        subtypes = [p.get_content_subtype() for p in alt.get_payload()]
        assert "html" in subtypes
        assert "calendar" in subtypes

    def test_meeting_without_ical(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(kind=eo.KIND_MEETING)
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        alt = msg.get_payload()[0]
        subtypes = [p.get_content_subtype() for p in alt.get_payload()]
        assert "html" in subtypes
        assert "calendar" not in subtypes

    def test_meeting_default_from_address(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(kind=eo.KIND_MEETING)
        msg = eo._build_mime(row, {"from_address": ""})
        assert msg["From"] == "portal@company.local"

    def test_generic_with_text_and_html(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(body_text="Hello plain", body_html="<p>Hi</p>")
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        assert msg.get_content_type() == "multipart/alternative"
        subtypes = [p.get_content_subtype() for p in msg.get_payload()]
        assert subtypes == ["plain", "html"]

    def test_generic_html_only(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(body_html="<p>Hi</p>")
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        parts = msg.get_payload()
        assert len(parts) == 1
        assert parts[0].get_content_subtype() == "html"

    def test_generic_default_from_address(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row()
        msg = eo._build_mime(row, {"from_address": ""})
        assert msg["From"] == "portal@company.local"

    def test_generic_with_inline_image_builds_related(self):
        import base64

        from app.worker.tasks import email_outbox as eo

        img = {
            "cid": "cover-1",
            "mime": "image/jpeg",
            "b64": base64.b64encode(b"\xff\xd8jpeg").decode("ascii"),
        }
        row = _mk_row(body_html='<img src="cid:cover-1">', inline_images=[img])
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        assert msg.get_content_type() == "multipart/related"
        parts = msg.get_payload()
        assert parts[0].get_content_type() == "multipart/alternative"
        image_part = parts[1]
        assert image_part.get_content_type() == "image/jpeg"
        assert image_part["Content-ID"] == "<cover-1>"
        assert "inline" in image_part["Content-Disposition"]

    def test_generic_without_inline_images_stays_alternative(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(body_html="<p>Hi</p>", inline_images=[])
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        assert msg.get_content_type() == "multipart/alternative"


# ── E3: MIME header injection ────────────────────────────────────────────


class TestHeaderInjection:
    """E3: CR/LF в subject/to (источник — booking.title / news_title из БД) не
    должны порождать дополнительные заголовки (Bcc/доп. получатели)."""

    def test_subject_crlf_stripped_meeting(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(
            kind=eo.KIND_MEETING,
            subject="Встреча\r\nBcc: victim@evil.com",
        )
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        # No injected Bcc header, and the raw serialized message has no CR/LF
        # smuggled inside the Subject value.
        assert msg["Bcc"] is None
        assert "\r" not in msg["Subject"]
        assert "\n" not in msg["Subject"]
        assert "victim@evil.com" in msg["Subject"]  # neutralized into the subject

    def test_to_crlf_stripped_generic(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row(to_email="ok@x.com\r\nBcc: victim@evil.com")
        msg = eo._build_mime(row, {"from_address": "noreply@x.com"})
        assert msg["Bcc"] is None
        assert "\r" not in msg["To"]
        assert "\n" not in msg["To"]

    def test_from_crlf_stripped(self):
        from app.worker.tasks import email_outbox as eo

        row = _mk_row()
        msg = eo._build_mime(row, {"from_address": "noreply@x.com\r\nBcc: victim@evil.com"})
        assert msg["Bcc"] is None
        assert "\r" not in msg["From"]
        assert "\n" not in msg["From"]

    def test_sanitize_header_helper(self):
        from app.worker.tasks import email_outbox as eo

        assert eo._sanitize_header("a\r\nb") == "a  b"
        assert eo._sanitize_header("") == ""
        assert eo._sanitize_header("plain") == "plain"
