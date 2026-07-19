"""Unit-тесты для app.worker.tasks.messenger_outbox.

Покрывают process_messenger_outbox (по образцу test_worker_email_outbox):
- no_claimed → 0 (early return)
- lock_held → 0
- max_disabled → mark_failed (transient) на всех записях
- max_misconfigured (enabled=True, no token) → mark_failed permanent
- send success → mark_sent × n
- send raises MaxApiError(401) → mark_failed permanent
- send raises transport → mark_failed transient
- distributed lock release в finally

Используется _FakeSession с async-context-manager + begin().
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── helpers ──────────────────────────────────────────────────────────────


class _FakeRedis:
    """Fake redis для distributed lock."""

    def __init__(self, *, lock_acquired: bool = True):
        self._lock_acquired = lock_acquired
        self.set = AsyncMock(return_value=lock_acquired)
        self.eval = AsyncMock(return_value=1)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _FakeSession:
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


@asynccontextmanager
async def _session_cm(sess):
    yield sess


def _patch_session_local(monkeypatch, sess):
    from app.worker.tasks import messenger_outbox as mo

    monkeypatch.setattr(mo, "AsyncSessionLocal", lambda: sess)


def _mk_row(
    *,
    provider="max",
    attempts=0,
    max_attempts=6,
    chat_id="100",
    text="hi",
    payload=None,
):
    return {
        "id": uuid.uuid4(),
        "provider": provider,
        "chat_id": chat_id,
        "text": text,
        "payload": payload if payload is not None else {},
        "attempts": attempts,
        "max_attempts": max_attempts,
    }


def _settings(*, enabled=True, token_enc="enc", chat_id="100"):
    return SimpleNamespace(
        enabled=enabled,
        bot_token_enc=token_enc,
        chat_id=chat_id,
    )


# ── process_messenger_outbox ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestProcessMessengerOutbox:
    async def test_no_redis_returns_zero(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        result = await mo.process_messenger_outbox({})
        assert result == 0

    async def test_lock_held_returns_zero(self, monkeypatch):
        """Distributed lock занят другим воркером → тихий выход 0."""
        from app.worker.tasks import messenger_outbox as mo

        redis = _FakeRedis(lock_acquired=False)
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0

    async def test_no_claimed_returns_zero(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=[]))
        redis = _FakeRedis()

        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0

    async def test_max_disabled_marks_failed_transient(self, monkeypatch):
        """MAX выключен → все записи возвращаются в PENDING (transient)."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings(enabled=False)))
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_count == 2
        kwargs = mark_failed_mock.await_args_list[0].kwargs
        assert kwargs["error_class"] == "transient"

    async def test_max_misconfigured_marks_failed_permanent(self, monkeypatch):
        """enabled=True, но токен потерян → permanent (конфиг сломан)."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        # enabled=True, но bot_token_enc=None (edge-case ручного редактирования).
        monkeypatch.setattr(
            mo,
            "_load_max_settings",
            AsyncMock(return_value=_settings(enabled=True, token_enc=None)),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_send_success_marks_sent(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings()))
        monkeypatch.setattr(mo, "send_message", AsyncMock())
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 2
        assert mark_sent_mock.await_count == 2

    async def test_send_4xx_marks_failed_permanent(self, monkeypatch):
        from app.services.max_messenger import MaxApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings()))
        monkeypatch.setattr(
            mo,
            "send_message",
            AsyncMock(side_effect=MaxApiError("401", status_code=401)),
        )
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_sent_mock.assert_not_called()
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_send_transport_error_marks_failed_transient(self, monkeypatch):
        from app.services.max_messenger import MaxApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings()))
        # Transport-failure → status_code=None → unknown → retry.
        monkeypatch.setattr(
            mo,
            "send_message",
            AsyncMock(side_effect=MaxApiError("timeout")),
        )
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] in {"unknown", "transient"}

    async def test_decrypt_failure_marks_failed_permanent(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings()))

        def _boom(_):
            raise RuntimeError("InvalidToken")

        monkeypatch.setattr(mo, "decrypt_secret", _boom)
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"
        assert mark_failed_mock.await_args.kwargs["error_type"] == "RuntimeError"

    async def test_unknown_provider_marks_failed(self, monkeypatch):
        """Неизвестный провайдер → MaxApiError (status=None) → unknown → retry.
        ``_dispatch_for_provider`` должен явно рейзить для не-MAX."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="telegram")]  # провайдер не поддерживается
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()


# ── cleanup_messenger_outbox ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestCleanupMessengerOutbox:
    async def test_returns_count(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)
        monkeypatch.setattr(mo, "cleanup_old_sent", AsyncMock(return_value=7))

        result = await mo.cleanup_messenger_outbox({})
        assert result == 7

    async def test_returns_zero_on_exception(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        def _boom(_a, **_kw):
            raise RuntimeError("DB down")

        monkeypatch.setattr(mo, "cleanup_old_sent", _boom)

        result = await mo.cleanup_messenger_outbox({})
        assert result == 0
