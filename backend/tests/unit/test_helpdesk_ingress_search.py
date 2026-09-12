"""Unit-тесты ``_search_all`` для helpdesk ingress.

Защита от регрессии: поллер должен забирать ВСЕ письма папки (``SEARCH ALL``),
а не только ``UNSEEN``. Раньше фильтр ``UNSEEN`` терял письма, которые оператор
прочитал в почтовом клиенте (или которые пришли уже ``\\Seen``). Дедупликация
при этом — на уровне ``helpdesk_email_log`` (см. ``_process_uid``).
"""

from __future__ import annotations

import pytest

from app.services.helpdesk.ingress import _search_all


class _FakeClient:
    """Минимальный fake aioimaplib-клиента: только ``search``."""

    def __init__(self, *, typ: str, data: list) -> None:
        self._typ = typ
        self._data = data

    async def search(self, criterion: str) -> tuple[str, list]:
        # Фиксируем, что ищем именно ALL, а не UNSEEN.
        self.last_criterion = criterion
        return self._typ, self._data


async def test_search_all_returns_all_uids() -> None:
    client = _FakeClient(typ="OK", data=[b"1 2 3"])
    uids = await _search_all(client)
    assert uids == ["1", "2", "3"]
    assert client.last_criterion == "ALL"


async def test_search_all_empty_when_no_messages() -> None:
    client = _FakeClient(typ="OK", data=[b""])
    assert await _search_all(client) == []


async def test_search_all_empty_when_no_data() -> None:
    client = _FakeClient(typ="OK", data=[])
    assert await _search_all(client) == []


async def test_search_all_empty_on_non_ok_status() -> None:
    # Сервер вернул NO/BUG — не падаем, отдаём пустой список.
    client = _FakeClient(typ="NO", data=[b"1 2"])
    assert await _search_all(client) == []


@pytest.mark.parametrize("payload", [b"1 2 3", "1 2 3"])
async def test_search_all_handles_bytes_and_str(payload: object) -> None:
    """ARQ-воркер использует Redis без ``decode_responses``, и некоторые
    IMAP-ответы тоже приходят как bytes — проверяем стойкость."""
    client = _FakeClient(typ="OK", data=[payload])
    assert await _search_all(client) == ["1", "2", "3"]
