"""Unit-тесты interval guard для ``poll_helpdesk_mailbox``.

Главная цель — защитить от регрессии баг, при котором ARQ-воркер использует
собственный Redis-клиент **без** ``decode_responses=True`` (в отличие от
``app.state.redis`` в lifespan). ``redis.get(LAST_POLL_KEY)`` тогда возвращает
``bytes``, и ``datetime.fromisoformat(last)`` поднимал ``TypeError``,
навсегда ломая поллинг после первого успешного цикла.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.worker.tasks.helpdesk as helpdesk_worker
from app.services.helpdesk.ingress import LAST_POLL_KEY


class _FakeRedis:
    """Минимальный fake redis: хранит ключи в dict, отдаёт bytes/str по флагу."""

    def __init__(self, *, store: dict[str, object], decode: bool) -> None:
        self._store = store
        self._decode = decode

    async def get(self, key: str) -> bytes | str | None:
        val = self._store.get(key)
        if val is None:
            return None
        if self._decode:
            return val if isinstance(val, str) else str(val)
        return val.encode() if isinstance(val, str) else cast("bytes | str", val)

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def eval(self, *_args: object, **_kwargs: object) -> int:
        return 1


@pytest.fixture
def _enabled_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обход module-gate: всегда включено."""
    monkeypatch.setattr(helpdesk_worker, "_module_enabled", AsyncMock(return_value=True))


@pytest.fixture
def _enabled_module_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module-gate: всегда выключено (для проверки раннего выхода)."""
    monkeypatch.setattr(helpdesk_worker, "_module_enabled", AsyncMock(return_value=False))


def _patch_session(monkeypatch: pytest.MonkeyPatch, settings_row: object) -> None:
    """``AsyncSessionLocal`` — это ``async_sessionmaker``; ``AsyncSessionLocal()``
    возвращает сессию (sync call), используемую через ``async with``.
    Подменяем на фабрику, возвращающую контекстный менеджер."""

    class _Q:
        async def execute(self, *a: object, **k: object) -> MagicMock:
            m = MagicMock()
            m.scalars.return_value.one_or_none.return_value = settings_row
            return m

    class _CM:
        async def __aenter__(self) -> _Q:
            return _Q()

        async def __aexit__(self, *a: object) -> None:
            return None

    def _factory() -> _CM:
        return _CM()

    monkeypatch.setattr(helpdesk_worker, "AsyncSessionLocal", _factory)


@pytest.mark.parametrize(
    "decode_responses",
    [True, False],
    ids=["decode_responses=True (app.state.redis)", "decode_responses=False (ARQ worker)"],
)
async def test_interval_guard_does_not_crash_on_bytes_or_str(
    decode_responses: bool, _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LAST_POLL_KEY`` с недавней меткой → skipped=interval_not_elapsed,
    причём независимо от того, bytes или str отдал Redis. Без фикса на bytes
    таск падал с ``TypeError: fromisoformat: argument must be str``."""
    recent = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    store: dict[str, object] = {LAST_POLL_KEY: recent}
    fake_redis = _FakeRedis(store=store, decode=decode_responses)

    settings_row = MagicMock()
    settings_row.poll_interval_seconds = 60
    _patch_session(monkeypatch, settings_row)

    result = await helpdesk_worker.poll_helpdesk_mailbox({"redis": fake_redis})
    assert result == {"skipped": "interval_not_elapsed"}


@pytest.mark.parametrize("decode_responses", [True, False])
async def test_poll_proceeds_when_interval_elapsed(
    decode_responses: bool, _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Метка в прошлом (> poll_interval) → поллинг идёт дальше (вызывает
    ``poll_mailbox``), а не падает на парсинге."""
    old = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    store: dict[str, object] = {LAST_POLL_KEY: old}
    fake_redis = _FakeRedis(store=store, decode=decode_responses)

    settings_row = MagicMock()
    settings_row.poll_interval_seconds = 60
    _patch_session(monkeypatch, settings_row)

    called = {}

    async def _fake_poll(db: object, redis: object, *, settings_row: object) -> dict:
        called["yes"] = True
        return {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(helpdesk_worker, "poll_mailbox", _fake_poll)

    result = await helpdesk_worker.poll_helpdesk_mailbox({"redis": fake_redis})
    assert called.get("yes") is True
    assert result["fetched"] == 0


# ---------------------------------------------------------------------------
# _module_enabled — gate проверяет modules.helpdesk.enabled через Redis.
# ---------------------------------------------------------------------------


async def test_module_enabled_returns_true_when_helpdesk_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.core import modules_config

    async def _fake_load(redis: object) -> SimpleNamespace:
        return SimpleNamespace(helpdesk=SimpleNamespace(enabled=True))

    monkeypatch.setattr(modules_config, "load_modules_shared", _fake_load)
    got = await helpdesk_worker._module_enabled(MagicMock())
    assert got is True


async def test_module_enabled_returns_false_when_helpdesk_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.core import modules_config

    async def _fake_load(redis: object) -> SimpleNamespace:
        return SimpleNamespace(helpdesk=SimpleNamespace(enabled=False))

    monkeypatch.setattr(modules_config, "load_modules_shared", _fake_load)
    got = await helpdesk_worker._module_enabled(MagicMock())
    assert got is False


# ---------------------------------------------------------------------------
# poll_helpdesk_mailbox — недостающие ветки (no redis, not_configured, lock_held).
# ---------------------------------------------------------------------------


async def test_poll_no_redis_returns_module_disabled() -> None:
    """``redis is None`` → выходим сразу (до module-gate)."""
    result = await helpdesk_worker.poll_helpdesk_mailbox({"redis": None})
    assert result == {"skipped": "module_disabled"}


async def test_poll_not_configured_when_no_settings(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Строки ``HelpdeskMailboxSettings`` нет → not_configured."""

    class _Q:
        async def execute(self, *a: object, **k: object) -> MagicMock:
            m = MagicMock()
            m.scalars.return_value.one_or_none.return_value = None
            return m

    class _CM:
        async def __aenter__(self) -> _Q:
            return _Q()

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(helpdesk_worker, "AsyncSessionLocal", lambda: _CM())

    store: dict[str, object] = {}
    fake_redis = _FakeRedis(store=store, decode=True)
    result = await helpdesk_worker.poll_helpdesk_mailbox({"redis": fake_redis})
    assert result == {"skipped": "not_configured"}


async def test_poll_lock_held_returns_skipped(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interval elapsed, но lock уже занят → lock_held."""
    settings_row = MagicMock()
    settings_row.poll_interval_seconds = 60
    _patch_session(monkeypatch, settings_row)

    # LAST_POLL_KEY отсутствует → интервал «прошёл», идём к lock. Lock занят.
    store: dict[str, object] = {"helpdesk:imap:poll_lock": "someone-else"}  # POLL_LOCK_KEY уже есть

    class _LockRedis(_FakeRedis):
        async def set(
            self, key: str, value: str, *, nx: bool = False, ex: int | None = None
        ) -> bool:
            if nx and key in self._store:
                return False
            self._store[key] = value
            return True

    fake_redis = _LockRedis(store=store, decode=True)
    result = await helpdesk_worker.poll_helpdesk_mailbox({"redis": fake_redis})
    assert result == {"skipped": "lock_held"}


# ---------------------------------------------------------------------------
# Helpers для archive/cleanup-задач (сессия с возвращаемыми id).
# ---------------------------------------------------------------------------


def _patch_session_returning_ids(monkeypatch: pytest.MonkeyPatch, ids: list) -> None:
    """Сессия, где execute возвращает результат с ``scalars().all()``."""

    class _Q:
        def __init__(self) -> None:
            self.committed = False

        async def execute(self, *a: object, **k: object) -> MagicMock:
            m = MagicMock()
            m.scalars.return_value.all.return_value = ids
            return m

        async def commit(self) -> None:
            self.committed = True

    class _CM:
        def __init__(self) -> None:
            self.q = _Q()

        async def __aenter__(self) -> _Q:
            return self.q

        async def __aexit__(self, *a: object) -> None:
            return None

    def _factory() -> object:
        return _CM()

    monkeypatch.setattr(helpdesk_worker, "AsyncSessionLocal", _factory)
    return None


# ---------------------------------------------------------------------------
# send_helpdesk_digest — schedule/идемпотентность/lock.
# ---------------------------------------------------------------------------


def _patch_digest_session(monkeypatch: pytest.MonkeyPatch, settings_row: object) -> None:
    """Сессия для schedule-check (one_or_none)."""

    class _Q:
        async def execute(self, *a: object, **k: object) -> MagicMock:
            m = MagicMock()
            m.scalars.return_value.one_or_none.return_value = settings_row
            return m

    class _CM:
        async def __aenter__(self) -> _Q:
            return _Q()

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(helpdesk_worker, "AsyncSessionLocal", lambda: _CM())


async def test_digest_no_redis_returns_disabled() -> None:
    result = await helpdesk_worker.send_helpdesk_digest({"redis": None})
    assert result == {"skipped": "module_disabled"}


async def test_digest_not_configured(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Строки digest-настроек нет → not_configured."""
    _patch_digest_session(monkeypatch, settings_row=None)
    result = await helpdesk_worker.send_helpdesk_digest(
        {"redis": _FakeRedis(store={}, decode=True)}
    )
    assert result == {"skipped": "not_configured"}


async def test_digest_schedule_mismatch(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should_send_today=False → schedule_mismatch."""
    settings_row = MagicMock()
    settings_row.enabled = True
    settings_row.digest_hour = 9
    settings_row.digest_minute = 0
    settings_row.digest_schedule = "daily"
    _patch_digest_session(monkeypatch, settings_row)

    monkeypatch.setattr(helpdesk_worker, "should_send_today", lambda now, **kw: False)

    result = await helpdesk_worker.send_helpdesk_digest(
        {"redis": _FakeRedis(store={}, decode=True)}
    )
    assert result == {"skipped": "schedule_mismatch"}


async def test_digest_already_sent_today(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Уже слали сегодня → already_sent_today."""
    settings_row = MagicMock()
    _patch_digest_session(monkeypatch, settings_row)

    monkeypatch.setattr(helpdesk_worker, "should_send_today", lambda now, **kw: True)
    monkeypatch.setattr(helpdesk_worker, "already_sent_today", lambda last, *, now: True)

    recent = datetime.now(UTC).isoformat()
    store: dict[str, object] = {"helpdesk:digest:last_sent_at": recent}
    result = await helpdesk_worker.send_helpdesk_digest(
        {"redis": _FakeRedis(store=store, decode=True)}
    )
    assert result == {"skipped": "already_sent_today"}


async def test_digest_lock_held(_enabled_module: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Schedule ок, не слали, но lock занят → lock_held."""
    settings_row = MagicMock()
    _patch_digest_session(monkeypatch, settings_row)

    monkeypatch.setattr(helpdesk_worker, "should_send_today", lambda now, **kw: True)
    monkeypatch.setattr(helpdesk_worker, "already_sent_today", lambda last, *, now: False)

    # DIGEST_LOCK_KEY уже занят.
    class _LockRedis(_FakeRedis):
        async def set(
            self, key: str, value: str, *, nx: bool = False, ex: int | None = None
        ) -> bool:
            if nx and key in self._store:
                return False
            self._store[key] = value
            return True

    store: dict[str, object] = {"helpdesk:digest:lock": "other"}
    result = await helpdesk_worker.send_helpdesk_digest(
        {"redis": _LockRedis(store=store, decode=True)}
    )
    assert result == {"skipped": "lock_held"}


async def test_digest_happy_path_calls_send_digests(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Все проверки пройдены → вызывается ``send_digests``."""
    settings_row = MagicMock()
    _patch_digest_session(monkeypatch, settings_row)

    monkeypatch.setattr(helpdesk_worker, "should_send_today", lambda now, **kw: True)
    monkeypatch.setattr(helpdesk_worker, "already_sent_today", lambda last, *, now: False)

    # load_system_settings → portal_base_url.
    fake_settings = MagicMock()
    fake_settings.portal_base_url = "https://portal.local"
    monkeypatch.setattr(helpdesk_worker, "load_system_settings", lambda: fake_settings)

    called = {}

    async def _fake_send(db, redis, *, portal_base_url, now):
        called["yes"] = True
        called["url"] = portal_base_url
        return {"sent": 3}

    monkeypatch.setattr(helpdesk_worker, "send_digests", _fake_send)

    result = await helpdesk_worker.send_helpdesk_digest(
        {"redis": _FakeRedis(store={}, decode=True)}
    )
    assert called.get("yes") is True
    assert called["url"] == "https://portal.local"
    assert result == {"sent": 3}


# ---------------------------------------------------------------------------
# archive/cleanup/partition — тонкие обёртки с module-gate.
# ---------------------------------------------------------------------------


async def test_archive_task_disabled_module(_enabled_module_false: None) -> None:
    result = await helpdesk_worker.archive_closed_tickets_task({"redis": MagicMock()})
    assert result == 0


async def test_cleanup_task_disabled_module(_enabled_module_false: None) -> None:
    result = await helpdesk_worker.cleanup_helpdesk_attachments_task({"redis": MagicMock()})
    assert result == 0


async def test_archive_task_calls_service(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = {}

    async def _fake_archive(db):
        called["yes"] = True
        return 5

    monkeypatch.setattr(helpdesk_worker, "archive_closed_tickets", _fake_archive)
    _patch_session_returning_ids(monkeypatch, ids=[])  # любая сессия подойдёт
    result = await helpdesk_worker.archive_closed_tickets_task(
        {"redis": _FakeRedis(store={}, decode=True)}
    )
    assert result == 5
    assert called.get("yes") is True


async def test_cleanup_task_calls_service(
    _enabled_module: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = {}

    async def _fake_cleanup(db):
        called["yes"] = True
        return 3

    monkeypatch.setattr(helpdesk_worker, "cleanup_archived_files", _fake_cleanup)
    _patch_session_returning_ids(monkeypatch, ids=[])
    result = await helpdesk_worker.cleanup_helpdesk_attachments_task(
        {"redis": _FakeRedis(store={}, decode=True)}
    )
    assert result == 3
    assert called.get("yes") is True
