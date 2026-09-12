"""Unit-тесты для app.worker.tasks.messenger_outbox.

Покрывают process_messenger_outbox (мульти-провайдерная диспетчеризация):
- no_claimed → 0 (early return); lock_held → 0
- MAX: disabled → transient; misconfigured → permanent; decrypt-fail →
  permanent; send success → mark_sent; 4xx → permanent; transport → transient
- Matrix: disabled → transient; misconfigured → permanent; decrypt-fail →
  permanent; send success (DM-resolve + txnId); 4xx → permanent; transport →
  transient; DM создаётся один раз на батч для дублей MXID
- mixed batch (max + matrix) обрабатывается обеими ветками
- unknown provider → permanent (не ретраим)
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


def _max_settings(*, enabled=True, token_enc="enc", chat_id="100"):
    return SimpleNamespace(enabled=enabled, bot_token_enc=token_enc, chat_id=chat_id)


def _matrix_settings(
    *,
    enabled=True,
    token_enc="enc",
    homeserver_url="https://matrix.mage.ru",
    bot_user_id="@portal-bot:matrix.mage.ru",
    server_name="matrix.mage.ru",
):
    return SimpleNamespace(
        enabled=enabled,
        access_token_enc=token_enc,
        homeserver_url=homeserver_url,
        bot_user_id=bot_user_id,
        server_name=server_name,
    )


class _FakeDmResolver:
    """Заглушка DmResolver: запоминает вызовы resolve без сетевых вызовов."""

    def __init__(self, *, rooms: dict[str, str] | None = None):
        self.rooms = rooms or {}
        self.resolve_calls: list[str] = []
        self.created: list[str] = []

    async def resolve(self, mxid: str) -> str:
        self.resolve_calls.append(mxid)
        if mxid not in self.rooms:
            self.created.append(mxid)
            self.rooms[mxid] = f"!room-{len(self.rooms)}:matrix.mage.ru"
        return self.rooms[mxid]


# ── process_messenger_outbox: общие ──────────────────────────────────────


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

    async def test_unknown_provider_marks_failed_permanent(self, monkeypatch):
        """Неизвестный провайдер → permanent fail без загрузки чьих-либо настроек."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="telegram")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        load_max = AsyncMock()
        load_matrix = AsyncMock()
        monkeypatch.setattr(mo, "_load_max_settings", load_max)
        monkeypatch.setattr(mo, "_load_matrix_settings", load_matrix)
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"
        load_max.assert_not_called()
        load_matrix.assert_not_called()


# ── MAX ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDispatchMax:
    async def test_max_disabled_marks_failed_transient(self, monkeypatch):
        """MAX выключен → все записи возвращаются в PENDING (transient)."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            mo, "_load_max_settings", AsyncMock(return_value=_max_settings(enabled=False))
        )
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
        monkeypatch.setattr(
            mo,
            "_load_max_settings",
            AsyncMock(return_value=_max_settings(enabled=True, token_enc=None)),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_max_send_success_marks_sent(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(), _mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))
        send_mock = AsyncMock()
        monkeypatch.setattr(mo, "max_send_message", send_mock)
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 2
        assert mark_sent_mock.await_count == 2
        assert send_mock.await_count == 2
        # chat_id из строки outbox приоритетен над настройками.
        kwargs = send_mock.await_args_list[0].kwargs
        assert kwargs["chat_id"] == "100"
        assert kwargs["bot_token"] == "decrypted-token"

    async def test_max_send_4xx_marks_failed_permanent(self, monkeypatch):
        from app.services.max_messenger import MaxApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))
        monkeypatch.setattr(
            mo,
            "max_send_message",
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

    async def test_max_send_transport_error_marks_failed_retryable(self, monkeypatch):
        from app.services.max_messenger import MaxApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))
        # Transport-failure → status_code=None → unknown → retry.
        monkeypatch.setattr(
            mo,
            "max_send_message",
            AsyncMock(side_effect=MaxApiError("timeout")),
        )
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "decrypted-token")
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] in {"unknown", "transient"}

    async def test_max_decrypt_failure_marks_failed_permanent(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row()]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))

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


# ── Matrix ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDispatchMatrix:
    async def test_matrix_disabled_marks_failed_transient(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@u:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            mo,
            "_load_matrix_settings",
            AsyncMock(return_value=_matrix_settings(enabled=False)),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "transient"

    @pytest.mark.parametrize(
        ("settings_kwargs", "missing"),
        [
            ({"token_enc": None}, "token"),
            ({"homeserver_url": None}, "url"),
            ({"bot_user_id": None}, "bot"),
        ],
    )
    async def test_matrix_misconfigured_marks_failed_permanent(
        self, monkeypatch, settings_kwargs, missing
    ):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@u:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(
            mo,
            "_load_matrix_settings",
            AsyncMock(return_value=_matrix_settings(**settings_kwargs)),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        mark_failed_mock.assert_awaited_once()
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"
        assert missing  # параметризация только для читаемости отчёта

    async def test_matrix_decrypt_failure_marks_failed_permanent(self, monkeypatch):
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@u:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))

        def _boom(_):
            raise RuntimeError("InvalidToken")

        monkeypatch.setattr(mo, "decrypt_secret", _boom)
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_matrix_send_success_resolves_dm_and_uses_txn_id(self, monkeypatch):
        """Успех: DM резолвится по MXID, txn_id = UUID outbox-строки,
        formatted_body из payload передаётся."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        row = _mk_row(
            provider="matrix",
            chat_id="@u:matrix.mage.ru",
            payload={"formatted_body": "<b>hi</b>"},
        )
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=[row]))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")

        fake_resolver = _FakeDmResolver()

        def _resolver_factory(**_kwargs):
            return fake_resolver

        monkeypatch.setattr(mo, "DmResolver", _resolver_factory)
        send_mock = AsyncMock(return_value={"event_id": "$1"})
        monkeypatch.setattr(mo, "matrix_send_message", send_mock)
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 1
        mark_sent_mock.assert_awaited_once()
        assert fake_resolver.resolve_calls == ["@u:matrix.mage.ru"]
        kwargs = send_mock.await_args.kwargs
        assert kwargs["txn_id"] == str(row["id"])
        assert kwargs["body"] == "hi"
        assert kwargs["formatted_body"] == "<b>hi</b>"
        assert kwargs["homeserver_url"] == "https://matrix.mage.ru"
        assert kwargs["access_token"] == "mct-token"
        assert kwargs["room_id"].startswith("!room-")

    async def test_matrix_dm_resolved_once_per_batch_for_same_mxid(self, monkeypatch):
        """Две строки одному MXID в одном батче → один резолв (кэш DmResolver)."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [
            _mk_row(provider="matrix", chat_id="@u:matrix.mage.ru"),
            _mk_row(provider="matrix", chat_id="@u:matrix.mage.ru"),
        ]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")

        fake_resolver = _FakeDmResolver()

        def _resolver_factory(**_kwargs):
            return fake_resolver

        monkeypatch.setattr(mo, "DmResolver", _resolver_factory)
        monkeypatch.setattr(mo, "matrix_send_message", AsyncMock())
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 2
        # Резолв кэшируется: второй вызов для того же MXID не создаёт комнату.
        assert fake_resolver.resolve_calls.count("@u:matrix.mage.ru") == 2
        assert fake_resolver.created == ["@u:matrix.mage.ru"]

    async def test_matrix_send_4xx_marks_failed_permanent(self, monkeypatch):
        """400 (в т.ч. несуществующий MXID-пользователь) → permanent."""
        from app.services.matrix_messenger import MatrixApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@ghost:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")
        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _FakeDmResolver())
        monkeypatch.setattr(
            mo,
            "matrix_send_message",
            AsyncMock(side_effect=MatrixApiError("nope", status_code=400, errcode="M_UNKNOWN")),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_matrix_dm_create_400_marks_failed_permanent(self, monkeypatch):
        """Пользователь не существует на homeserver → createRoom 400 → permanent."""
        from app.services.matrix_messenger import MatrixApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@ghost:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")

        class _BoomResolver:
            async def resolve(self, mxid: str) -> str:
                raise MatrixApiError("unknown user", status_code=400, errcode="M_UNKNOWN")

        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _BoomResolver())
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] == "permanent"

    async def test_matrix_rate_limit_429_marks_failed_transient(self, monkeypatch):
        from app.services.matrix_messenger import MatrixApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@u:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")
        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _FakeDmResolver())
        monkeypatch.setattr(
            mo,
            "matrix_send_message",
            AsyncMock(
                side_effect=MatrixApiError("limit", status_code=429, errcode="M_LIMIT_EXCEEDED")
            ),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] == "transient"

    async def test_matrix_transport_error_marks_failed_retryable(self, monkeypatch):
        from app.services.matrix_messenger import MatrixApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [_mk_row(provider="matrix", chat_id="@u:matrix.mage.ru")]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "mct-token")
        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _FakeDmResolver())
        monkeypatch.setattr(
            mo,
            "matrix_send_message",
            AsyncMock(side_effect=MatrixApiError("transport")),
        )
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 0
        assert mark_failed_mock.await_args.kwargs["error_class"] in {"unknown", "transient"}


# ── mixed batch ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMixedBatch:
    async def test_max_and_matrix_rows_dispatched_independently(self, monkeypatch):
        """Один батч со строками обоих провайдеров: каждая группа — своими
        настройками/клиентом, обе успешно отправлены."""
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [
            _mk_row(provider="max", chat_id="100"),
            _mk_row(provider="matrix", chat_id="@u:matrix.mage.ru"),
        ]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "tok")
        max_send = AsyncMock()
        matrix_send = AsyncMock(return_value={"event_id": "$1"})
        monkeypatch.setattr(mo, "max_send_message", max_send)
        monkeypatch.setattr(mo, "matrix_send_message", matrix_send)
        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _FakeDmResolver())
        mark_sent_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 2
        max_send.assert_awaited_once()
        matrix_send.assert_awaited_once()
        assert mark_sent_mock.await_count == 2

    async def test_max_failure_does_not_block_matrix(self, monkeypatch):
        """Сбой MAX-отправки не мешает matrix-строке (изоляция групп)."""
        from app.services.max_messenger import MaxApiError
        from app.worker.tasks import messenger_outbox as mo

        sess = _FakeSession()
        _patch_session_local(monkeypatch, sess)

        rows = [
            _mk_row(provider="max", chat_id="100"),
            _mk_row(provider="matrix", chat_id="@u:matrix.mage.ru"),
        ]
        monkeypatch.setattr(mo, "claim_pending", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo, "_load_max_settings", AsyncMock(return_value=_max_settings()))
        monkeypatch.setattr(mo, "_load_matrix_settings", AsyncMock(return_value=_matrix_settings()))
        monkeypatch.setattr(mo, "decrypt_secret", lambda x: "tok")
        monkeypatch.setattr(
            mo,
            "max_send_message",
            AsyncMock(side_effect=MaxApiError("403", status_code=403)),
        )
        monkeypatch.setattr(mo, "matrix_send_message", AsyncMock(return_value={"event_id": "$1"}))
        monkeypatch.setattr(mo, "DmResolver", lambda **_kw: _FakeDmResolver())
        mark_sent_mock = AsyncMock()
        mark_failed_mock = AsyncMock()
        monkeypatch.setattr(mo, "mark_sent", mark_sent_mock)
        monkeypatch.setattr(mo, "mark_failed", mark_failed_mock)

        redis = _FakeRedis()
        result = await mo.process_messenger_outbox({"redis": redis})
        assert result == 1
        mark_sent_mock.assert_awaited_once()
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
