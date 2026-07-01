"""Unit-тесты interval guard для ``poll_helpdesk_mailbox``.

Главная цель — защитить от регрессии баг, при котором ARQ-воркер использует
собственный Redis-клиент **без** ``decode_responses=True`` (в отличие от
``app.state.redis`` в lifespan). ``redis.get(LAST_POLL_KEY)`` тогда возвращает
``bytes``, и ``datetime.fromisoformat(last)`` поднимал ``TypeError``,
навсегда ломая поллинг после первого успешного цикла.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.worker.tasks.helpdesk as helpdesk_worker


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
        return val.encode() if isinstance(val, str) else val

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
    store = {helpdesk_worker.LAST_POLL_KEY: recent}
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
    store = {helpdesk_worker.LAST_POLL_KEY: old}
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
