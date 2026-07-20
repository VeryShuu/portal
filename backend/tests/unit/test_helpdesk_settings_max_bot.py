"""Unit-тесты для ``/helpdesk/settings/max-bot`` (GET/PUT/POST test).

Покрывает:
- GET: возвращает singleton (засевается миграцией 081) с configured=False по
  умолчанию (enabled=False, no token/chat_id).
- PUT: write-only токен (пусто = прежний шифр), сохраняет chat_id/enabled.
- PUT: enabled=True без токена (на момент сохранения и в БД) → 400.
- PUT: enabled=True без chat_id → 400.
- PUT: enabled=True при ранее сохранённом токене + новом chat_id → OK.
- PUT: диспатчит audit-event после commit.
- POST /test: успех (get_me вернул профиль) → ok=True, detail с именем.
- POST /test: исключение маскируется (defence-in-depth, как mailbox-test H-9).
- POST /test: токен не настроен → ok=False с generic-сообщением.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.helpdesk.settings import (
    get_max_bot_settings,
    put_max_bot_settings,
)
from app.api.helpdesk.settings import (
    test_max_bot_connection as max_bot_test_endpoint,
)
from app.schemas.helpdesk import (
    HelpdeskMaxBotSettingsIn,
    HelpdeskMaxBotSettingsOut,
    HelpdeskMaxBotTestResult,
)


def _admin() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@portal.local",
        role="admin",
        full_name="Админ Тестов",
    )


def _row(
    *,
    enabled: bool = False,
    bot_token_enc: str | None = None,
    chat_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=enabled,
        bot_token_enc=bot_token_enc,
        chat_id=chat_id,
        updated_at=datetime.now(UTC),
        updated_by_user_id=None,
    )


def _make_db_with_row(row: SimpleNamespace | None) -> tuple[MagicMock, MagicMock]:
    """Возвращает (db, row_mock) — заглушку, где execute возвращает row через
    ``.scalars().one_or_none()``. ``row_mock`` позволяет проверять мутации."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db, row


@pytest.mark.asyncio
class TestGetMaxBotSettings:
    async def test_returns_existing_row(self):
        db, _ = _make_db_with_row(_row(enabled=True, bot_token_enc="enc", chat_id="100"))
        out = await get_max_bot_settings(_admin(), db)
        assert isinstance(out, HelpdeskMaxBotSettingsOut)
        assert out.enabled is True
        assert out.bot_token_set is True
        assert out.chat_id == "100"
        assert out.configured is True  # enabled AND token AND chat_id

    async def test_unconfigured_when_no_token(self):
        db, _ = _make_db_with_row(_row(enabled=False))
        out = await get_max_bot_settings(_admin(), db)
        assert out.configured is False
        assert out.bot_token_set is False

    async def test_unconfigured_when_enabled_but_no_chat(self):
        """enabled=True, есть токен, но chat_id=None → configured=False
        (настройки неполные, уведомления не пойдут)."""
        db, _ = _make_db_with_row(_row(enabled=True, bot_token_enc="enc", chat_id=None))
        out = await get_max_bot_settings(_admin(), db)
        assert out.configured is False


@pytest.mark.asyncio
class TestPutMaxBotSettings:
    async def test_write_only_token_keeps_previous(self):
        """Пустой bot_token в payload → прежний шифр остаётся."""
        db, row = _make_db_with_row(_row(bot_token_enc="previous-enc"))
        redis = MagicMock()
        redis.publish = AsyncMock()  # push_audit_event → Redis XADD

        with (
            patch("app.api.helpdesk.settings.encrypt_secret") as enc_mock,
            patch("app.api.helpdesk.settings.push_audit_event", new=AsyncMock()),
        ):
            await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=True, chat_id="100"),
                _admin(),
                db,
                redis,
            )

        # encrypt не вызывается — прежний шифр сохранён.
        enc_mock.assert_not_called()
        assert row.bot_token_enc == "previous-enc"
        assert row.chat_id == "100"
        assert row.enabled is True

    async def test_new_token_encrypts(self):
        db, row = _make_db_with_row(_row())
        redis = MagicMock()

        with (
            patch("app.api.helpdesk.settings.encrypt_secret", return_value="new-enc") as enc_mock,
            patch("app.api.helpdesk.settings.push_audit_event", new=AsyncMock()),
        ):
            await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=True, bot_token="plaintext-token", chat_id="100"),
                _admin(),
                db,
                redis,
            )

        enc_mock.assert_called_once_with("plaintext-token")
        assert row.bot_token_enc == "new-enc"

    async def test_enabled_without_token_and_no_previous_raises_400(self):
        from fastapi import HTTPException

        db, _ = _make_db_with_row(_row(bot_token_enc=None))
        redis = MagicMock()

        with pytest.raises(HTTPException) as ei:
            await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=True, chat_id="100"),
                _admin(),
                db,
                redis,
            )
        assert ei.value.status_code == 400
        assert "bot_token" in ei.value.detail

    async def test_enabled_without_chat_id_raises_400(self):
        from fastapi import HTTPException

        db, _ = _make_db_with_row(_row(bot_token_enc="enc"))
        redis = MagicMock()

        with pytest.raises(HTTPException) as ei:
            await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=True, chat_id=None),
                _admin(),
                db,
                redis,
            )
        assert ei.value.status_code == 400
        assert "chat_id" in ei.value.detail

    async def test_disabled_without_token_ok(self):
        """Выключение канала не требует наличия кредов."""
        db, row = _make_db_with_row(_row(enabled=True, bot_token_enc=None))
        redis = MagicMock()

        with patch("app.api.helpdesk.settings.push_audit_event", new=AsyncMock()):
            out = await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=False, chat_id="100"),
                _admin(),
                db,
                redis,
            )
        assert row.enabled is False
        assert out.enabled is False

    async def test_audit_event_dispatched(self):
        db, _ = _make_db_with_row(_row(bot_token_enc="enc"))
        redis = MagicMock()

        with patch("app.api.helpdesk.settings.push_audit_event", new=AsyncMock()) as audit_mock:
            await put_max_bot_settings(
                HelpdeskMaxBotSettingsIn(enabled=True, chat_id="100", bot_token="x"),
                _admin(),
                db,
                redis,
            )
        audit_mock.assert_awaited_once()
        kwargs = audit_mock.await_args.kwargs
        assert kwargs["event_type"] == "helpdesk.max_bot_settings_changed"
        assert kwargs["resource_type"] == "helpdesk_max_bot_settings"
        assert kwargs["metadata"]["enabled"] is True
        assert kwargs["metadata"]["token_changed"] is True


@pytest.mark.asyncio
class TestMaxBotTestConnectionEndpoint:
    async def test_no_token_returns_ok_false(self):
        db, _ = _make_db_with_row(_row(bot_token_enc=None))
        result = await max_bot_test_endpoint(_admin(), db)
        assert isinstance(result, HelpdeskMaxBotTestResult)
        assert result.ok is False
        assert "not configured" in (result.error or "").lower()

    async def test_no_chat_id_returns_ok_false(self):
        """Нет chat_id → нельзя отправить тест (некуда)."""
        db, _ = _make_db_with_row(_row(bot_token_enc="enc", chat_id=None))
        result = await max_bot_test_endpoint(_admin(), db)
        assert result.ok is False
        assert "chat" in (result.error or "").lower()

    async def test_success_sends_message_and_returns_chat_id(self):
        """Тест-кнопка вызывает ``send_message`` (НЕ ``get_me``) — пользователь
        видит сообщение в чате как подтверждение работы."""
        db, _ = _make_db_with_row(_row(bot_token_enc="enc", chat_id="-100"))

        with (
            patch("app.api.helpdesk.settings.decrypt_secret", return_value="plain"),
            patch(
                "app.services.max_messenger.send_message",
                new=AsyncMock(return_value={"message": {"mid": "1"}}),
            ) as send_mock,
        ):
            result = await max_bot_test_endpoint(_admin(), db)

        send_mock.assert_awaited_once()
        # chat_id из настроек пробрасывается в send_message.
        assert send_mock.await_args.kwargs["chat_id"] == "-100"
        # Текст содержит маркер «Тест портала».
        assert "Тест портала" in send_mock.await_args.kwargs["text"]
        assert result.ok is True
        assert "-100" in (result.detail or "")

    async def test_exception_is_masked(self):
        """H-9 (defence-in-depth): исключение из MAX API (может содержать часть
        токена или чувствительные детали) не утекает в HTTP-ответ; вместо этого
        пользователь видит подсказку с диагнозом по HTTP-коду."""
        db, _ = _make_db_with_row(_row(bot_token_enc="enc", chat_id="-100"))

        secret_msg = "Unauthorized for token=SECRET-TOKEN-123"
        with (
            patch("app.api.helpdesk.settings.decrypt_secret", return_value="SECRET-TOKEN-123"),
            patch(
                "app.services.max_messenger.send_message",
                new=AsyncMock(side_effect=RuntimeError(secret_msg)),
            ),
        ):
            result = await max_bot_test_endpoint(_admin(), db)

        assert result.ok is False
        # Токен не утёк в маскированное сообщение.
        assert "SECRET-TOKEN-123" not in (result.error or "")

    async def test_404_returns_membership_hint(self):
        """404 от MAX = бот не состоит в чате → подсказка про membership."""
        from app.services.max_messenger import MaxApiError

        db, _ = _make_db_with_row(_row(bot_token_enc="enc", chat_id="-100"))
        with (
            patch("app.api.helpdesk.settings.decrypt_secret", return_value="tok"),
            patch(
                "app.services.max_messenger.send_message",
                new=AsyncMock(side_effect=MaxApiError("not found", status_code=404)),
            ),
        ):
            result = await max_bot_test_endpoint(_admin(), db)
        assert result.ok is False
        assert "chat not found" in (result.error or "").lower()
        assert "member" in (result.error or "").lower()

    async def test_401_returns_token_hint(self):
        from app.services.max_messenger import MaxApiError

        db, _ = _make_db_with_row(_row(bot_token_enc="enc", chat_id="-100"))
        with (
            patch("app.api.helpdesk.settings.decrypt_secret", return_value="tok"),
            patch(
                "app.services.max_messenger.send_message",
                new=AsyncMock(side_effect=MaxApiError("bad token", status_code=401)),
            ),
        ):
            result = await max_bot_test_endpoint(_admin(), db)
        assert result.ok is False
        assert "token" in (result.error or "").lower()
