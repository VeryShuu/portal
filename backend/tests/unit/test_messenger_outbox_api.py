"""Unit-тесты для ``/admin/messenger-outbox`` (валидация фильтров, row-маппинг).

SQL-пути (список/пагинация) покрываются integration-тестами на реальной БД;
здесь — тонкий HTTP-слой: whitelist-фильтры, escape, формат ответа.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.messenger_outbox import (
    _like_escape,
    get_outbox_item,
    list_outbox,
)


class TestLikeEscape:
    def test_escapes_percent(self):
        assert _like_escape("100%") == "100\\%"

    def test_escapes_underscore(self):
        assert _like_escape("a_b") == "a\\_b"

    def test_escapes_backslash_first(self):
        assert _like_escape("a\\b") == "a\\\\b"

    def test_plain_text_untouched(self):
        assert _like_escape("@user:matrix.mage.ru") == "@user:matrix.mage.ru"


def _row_mapping(**overrides) -> dict:
    """RowMapping-заглушка (dict с подписками) со всеми колонками list-запроса."""
    base: dict = {
        "id": uuid.uuid4(),
        "provider": "matrix",
        "chat_id": "@u:matrix.mage.ru",
        "text": "Привет! Длинный текст сообщения.",
        "payload": {"formatted_body": "<b>Привет!</b>"},
        "status": "SENT",
        "attempts": 1,
        "max_attempts": 6,
        "next_attempt_at": datetime.now(UTC),
        "last_error": None,
        "last_error_type": None,
        "last_error_class": None,
        "related_resource_type": None,
        "related_resource_id": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "sent_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestListOutboxFilters:
    async def test_invalid_status_raises_422(self, monkeypatch):
        with pytest.raises(HTTPException) as ei:
            await list_outbox(object(), object(), status_filter="BOGUS")
        assert ei.value.status_code == 422

    async def test_invalid_provider_raises_422(self, monkeypatch):
        with pytest.raises(HTTPException) as ei:
            await list_outbox(object(), object(), provider="telegram")
        assert ei.value.status_code == 422

    async def test_valid_provider_and_status_pass(self, monkeypatch):
        """Допустимые значения фильтров не рейзят; список формируется из репо."""
        from app.api import messenger_outbox as mo_module

        monkeypatch.setattr(mo_module.repo, "count_outbox", AsyncMock(return_value=1))
        monkeypatch.setattr(
            mo_module.repo,
            "list_outbox",
            AsyncMock(return_value=[_row_mapping()]),
        )
        monkeypatch.setattr(
            mo_module.repo, "counts_by_status_last_30d", AsyncMock(return_value={"SENT": 1})
        )

        result = await list_outbox(
            object(),
            object(),
            status_filter="SENT",
            provider="matrix",
            limit=50,
        )
        assert result["total"] == 1
        assert result["has_more"] is False
        item = result["items"][0]
        assert item["provider"] == "matrix"
        assert item["chat_id"] == "@u:matrix.mage.ru"
        # В списке — превью текста; полный text только в карточке записи.
        assert "text_preview" in item
        assert "text" not in item

    async def test_default_response_shape(self, monkeypatch):
        from app.api import messenger_outbox as mo_module

        rows = [_row_mapping(), _row_mapping(provider="max", chat_id="100")]
        monkeypatch.setattr(mo_module.repo, "count_outbox", AsyncMock(return_value=2))
        monkeypatch.setattr(mo_module.repo, "list_outbox", AsyncMock(return_value=rows))
        monkeypatch.setattr(mo_module.repo, "counts_by_status_last_30d", AsyncMock(return_value={}))

        result = await list_outbox(object(), object(), limit=50, offset=0)
        assert result["limit"] == 50
        assert result["offset"] == 0
        assert len(result["items"]) == 2


@pytest.mark.asyncio
class TestGetOutboxItem:
    async def test_returns_full_text_and_payload(self, monkeypatch):
        from app.api import messenger_outbox as mo_module

        row = _row_mapping()
        monkeypatch.setattr(mo_module.repo, "get_outbox_item", AsyncMock(return_value=row))

        result = await get_outbox_item(row["id"], object(), object())
        assert result["text"] == row["text"]
        assert result["payload"] == row["payload"]
        assert result["provider"] == "matrix"

    async def test_missing_returns_404(self, monkeypatch):
        from app.api import messenger_outbox as mo_module

        monkeypatch.setattr(mo_module.repo, "get_outbox_item", AsyncMock(return_value=None))
        with pytest.raises(HTTPException) as ei:
            await get_outbox_item(uuid.uuid4(), object(), object())
        assert ei.value.status_code == 404
