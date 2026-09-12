"""Unit-тесты для ``/admin/matrix-bot`` (GET/PUT/POST test).

Зеркалируют ``test_helpdesk_settings_max_bot.py``:
- GET: singleton, configured=False по умолчанию; configured = enabled AND
  token AND homeserver_url AND bot_user_id AND server_name.
- PUT: write-only токен (пусто = прежний шифр); enabled=True без обязательных
  полей → 400 (перечисление отсутствующих); audit-event диспатчится.
- POST /test: без токена/url/bot_user_id → ok=False generic; whoami 401 →
  подсказка про перевыпуск токена; успех → сообщение в DM админа по
  MXID-конвенции из его email.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.api.matrix_bot import (
    get_matrix_bot_settings,
    put_matrix_bot_settings,
)
from app.api.matrix_bot import test_matrix_bot_connection as matrix_bot_test_endpoint
from app.schemas.matrix_bot import (
    MatrixBotSettingsIn,
    MatrixBotSettingsOut,
    MatrixBotTestIn,
)


def _admin() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="admin@mage.ru",
        role="admin",
        full_name="Админ Тестов",
    )


def _row(
    *,
    enabled: bool = False,
    access_token_enc: str | None = None,
    homeserver_url: str | None = None,
    server_name: str = "matrix.mage.ru",
    bot_user_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=enabled,
        access_token_enc=access_token_enc,
        homeserver_url=homeserver_url,
        server_name=server_name,
        bot_user_id=bot_user_id,
        updated_at=datetime.now(UTC),
        updated_by_user_id=None,
    )


def _configured_row() -> SimpleNamespace:
    return _row(
        enabled=True,
        access_token_enc="enc",
        homeserver_url="https://matrix.mage.ru",
        bot_user_id="@portal-bot:matrix.mage.ru",
    )


def _make_db_with_row(row: SimpleNamespace | None) -> tuple[MagicMock, SimpleNamespace | None]:
    """Заглушка db: execute → row через ``.scalars().one_or_none()``."""
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
class TestGetMatrixBotSettings:
    async def test_returns_existing_row(self):
        db, _ = _make_db_with_row(_configured_row())
        out = await get_matrix_bot_settings(_admin(), db)
        assert isinstance(out, MatrixBotSettingsOut)
        assert out.enabled is True
        assert out.access_token_set is True
        assert out.homeserver_url == "https://matrix.mage.ru"
        assert out.configured is True

    async def test_unconfigured_when_no_token(self):
        db, _ = _make_db_with_row(_row(homeserver_url="https://m", bot_user_id="@b:s"))
        out = await get_matrix_bot_settings(_admin(), db)
        assert out.configured is False
        assert out.access_token_set is False

    async def test_unconfigured_when_enabled_but_no_bot_user_id(self):
        db, _ = _make_db_with_row(
            _row(enabled=True, access_token_enc="enc", homeserver_url="https://m")
        )
        out = await get_matrix_bot_settings(_admin(), db)
        assert out.configured is False


@pytest.mark.asyncio
class TestPutMatrixBotSettings:
    async def test_write_only_token_keeps_previous(self):
        """Пустой access_token в payload → прежний шифр остаётся."""
        db, row = _make_db_with_row(_row(access_token_enc="previous-enc"))
        redis = MagicMock()

        with (
            patch("app.api.matrix_bot.encrypt_secret") as enc_mock,
            patch("app.api.matrix_bot.push_audit_event", new=AsyncMock()) as audit_mock,
        ):
            await put_matrix_bot_settings(
                MatrixBotSettingsIn(
                    enabled=True,
                    homeserver_url="https://matrix.mage.ru",
                    bot_user_id="@portal-bot:matrix.mage.ru",
                ),
                _admin(),
                db,
                redis,
            )

        enc_mock.assert_not_called()
        assert row.access_token_enc == "previous-enc"
        assert row.enabled is True
        assert row.homeserver_url == "https://matrix.mage.ru"
        audit_mock.assert_awaited_once()

    async def test_new_token_encrypts(self):
        db, row = _make_db_with_row(_configured_row())
        redis = MagicMock()

        with (
            patch("app.api.matrix_bot.encrypt_secret", return_value="new-enc") as enc_mock,
            patch("app.api.matrix_bot.push_audit_event", new=AsyncMock()),
        ):
            await put_matrix_bot_settings(
                MatrixBotSettingsIn(
                    enabled=True,
                    access_token="mct_new",
                    homeserver_url="https://matrix.mage.ru",
                    bot_user_id="@portal-bot:matrix.mage.ru",
                ),
                _admin(),
                db,
                redis,
            )

        enc_mock.assert_called_once_with("mct_new")
        assert row.access_token_enc == "new-enc"

    async def test_enabled_without_required_fields_returns_400(self):
        db, _row_mock = _make_db_with_row(_row())
        redis = MagicMock()

        with (
            patch("app.api.matrix_bot.push_audit_event", new=AsyncMock()),
            pytest.raises(Exception) as ei,
        ):
            await put_matrix_bot_settings(
                MatrixBotSettingsIn(enabled=True),
                _admin(),
                db,
                redis,
            )
        assert getattr(ei.value, "status_code", None) == 400
        detail = str(ei.value.detail)
        # Перечислены все отсутствующие поля.
        for field in ("access_token", "homeserver_url", "bot_user_id"):
            assert field in detail

    async def test_enabled_with_saved_token_and_new_fields_ok(self):
        """Токен сохранён ранее + остальные поля в payload → включение проходит."""
        db, _row_mock = _make_db_with_row(_row(access_token_enc="enc"))
        redis = MagicMock()

        with (
            patch("app.api.matrix_bot.encrypt_secret") as enc_mock,
            patch("app.api.matrix_bot.push_audit_event", new=AsyncMock()),
        ):
            out = await put_matrix_bot_settings(
                MatrixBotSettingsIn(
                    enabled=True,
                    homeserver_url="https://matrix.mage.ru",
                    bot_user_id="@portal-bot:matrix.mage.ru",
                ),
                _admin(),
                db,
                redis,
            )

        enc_mock.assert_not_called()
        assert out.enabled is True
        assert out.configured is True


@pytest.mark.asyncio
class TestMatrixBotTestEndpoint:
    async def test_not_configured_returns_generic_error(self):
        db, _ = _make_db_with_row(_row())
        result = await matrix_bot_test_endpoint(_admin(), db)
        assert result.ok is False
        assert "token" in (result.error or "").lower()

    async def test_whoami_401_hints_token_reissue(self):
        from app.services.matrix_messenger import MatrixApiError

        db, _ = _make_db_with_row(_configured_row())
        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(
                    side_effect=MatrixApiError("401", status_code=401, errcode="M_UNKNOWN_TOKEN")
                ),
            ) as whoami_mock,
        ):
            result = await matrix_bot_test_endpoint(_admin(), db)

        whoami_mock.assert_awaited_once()
        assert result.ok is False
        assert "issue-compatibility-token" in (result.error or "")

    async def test_success_enqueues_to_outbox_for_admin_mxid(self):
        """Успех: сообщение ставится в messenger_outbox (настоящий путь
        доставки, видно в «Очереди мессенджеров»), получатель — по конвенции."""
        db, _ = _make_db_with_row(_configured_row())
        enqueue_mock = AsyncMock()

        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(return_value={"user_id": "@portal-bot:matrix.mage.ru"}),
            ),
            patch("app.api.matrix_bot.enqueue_messenger_message", enqueue_mock),
        ):
            result = await matrix_bot_test_endpoint(_admin(), db)

        assert result.ok is True
        kwargs = enqueue_mock.await_args.kwargs
        assert kwargs["provider"] == "matrix"
        assert kwargs["chat_id"] == "@admin:matrix.mage.ru"
        assert kwargs["related_resource_type"] == "matrix_bot_test"
        assert "Админ Тестов" in kwargs["text"]
        assert "<b>" in kwargs["payload"]["formatted_body"]
        assert "queued" in (result.detail or "")
        db.commit.assert_awaited_once()

    async def test_explicit_mxid_target_used_verbatim(self):
        """body.target = полный MXID → используется как есть (локальный админ
        с другим MXID тестирует доставку конкретному сотруднику)."""
        db, _ = _make_db_with_row(_configured_row())
        enqueue_mock = AsyncMock()

        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(return_value={"user_id": "@portal-bot:matrix.mage.ru"}),
            ),
            patch("app.api.matrix_bot.enqueue_messenger_message", enqueue_mock),
        ):
            result = await matrix_bot_test_endpoint(
                _admin(),
                db,
                MatrixBotTestIn(target="@borzihin.vs:matrix.mage.ru"),
            )

        assert result.ok is True
        assert enqueue_mock.await_args.kwargs["chat_id"] == "@borzihin.vs:matrix.mage.ru"
        assert "@borzihin.vs:matrix.mage.ru" in (result.detail or "")

    async def test_email_target_derived_via_convention(self):
        db, _ = _make_db_with_row(_configured_row())
        enqueue_mock = AsyncMock()

        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(return_value={"user_id": "@portal-bot:matrix.mage.ru"}),
            ),
            patch("app.api.matrix_bot.enqueue_messenger_message", enqueue_mock),
        ):
            await matrix_bot_test_endpoint(_admin(), db, MatrixBotTestIn(target="Ivanov.P@mage.ru"))

        assert enqueue_mock.await_args.kwargs["chat_id"] == "@ivanov.p:matrix.mage.ru"

    async def test_localpart_target_derived_with_server_name(self):
        db, _ = _make_db_with_row(_configured_row())
        enqueue_mock = AsyncMock()

        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(return_value={"user_id": "@portal-bot:matrix.mage.ru"}),
            ),
            patch("app.api.matrix_bot.enqueue_messenger_message", enqueue_mock),
        ):
            await matrix_bot_test_endpoint(_admin(), db, MatrixBotTestIn(target="Petrov.SS"))

        assert enqueue_mock.await_args.kwargs["chat_id"] == "@petrov.ss:matrix.mage.ru"

    async def test_enqueue_failure_returns_error_without_crash(self):
        """Сбой записи в outbox (БД) → ok=False с типом исключения."""
        db, _ = _make_db_with_row(_configured_row())

        with (
            patch("app.api.matrix_bot.decrypt_secret", return_value="tok"),
            patch(
                "app.api.matrix_bot.whoami",
                new=AsyncMock(return_value={"user_id": "@portal-bot:matrix.mage.ru"}),
            ),
            patch(
                "app.api.matrix_bot.enqueue_messenger_message",
                AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            result = await matrix_bot_test_endpoint(_admin(), db)

        assert result.ok is False
        assert "RuntimeError" in (result.error or "")


class TestMatrixBotSettingsInValidation:
    """Схемные валидации (Pydantic-уровень, без db)."""

    def test_homeserver_url_requires_scheme(self):
        with pytest.raises(ValidationError):
            MatrixBotSettingsIn(homeserver_url="matrix.mage.ru")

    def test_server_name_lowercased(self):
        dto = MatrixBotSettingsIn(server_name="Matrix.Mage.RU")
        assert dto.server_name == "matrix.mage.ru"

    def test_bot_user_id_lowercased(self):
        dto = MatrixBotSettingsIn(bot_user_id="@Portal-Bot:Matrix.Mage.RU")
        assert dto.bot_user_id == "@portal-bot:matrix.mage.ru"

    def test_access_token_stripped(self):
        """Хвостовой пробел/перенос при вставке из mas-cli — стриппится
        (иначе h11 отклоняет Bearer-заголовок «Illegal header value»)."""
        dto = MatrixBotSettingsIn(access_token="  mct_x\t\n")
        assert dto.access_token == "mct_x"

    def test_access_token_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            MatrixBotSettingsIn(access_token="   ")

    def test_explicit_nulls_pass_through(self):
        """Явный null (= «не менять», write-only семантика) проходит
        валидаторы всех полей. На unset-полях Pydantic валидаторы не
        запускает — поэтому null передаём явно."""
        dto = MatrixBotSettingsIn(
            access_token=None,
            homeserver_url=None,
            server_name=None,
            bot_user_id=None,
        )
        assert dto.access_token is None
        assert dto.homeserver_url is None
        assert dto.server_name is None
        assert dto.bot_user_id is None

    def test_homeserver_url_stripped(self):
        dto = MatrixBotSettingsIn(homeserver_url="  https://matrix.mage.ru ")
        assert dto.homeserver_url == "https://matrix.mage.ru"

    def test_homeserver_url_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            MatrixBotSettingsIn(homeserver_url="   ")

    def test_server_name_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            MatrixBotSettingsIn(server_name=" ")

    def test_bot_user_id_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            MatrixBotSettingsIn(bot_user_id=" ")


class TestResolveTestTarget:
    """Резолюция цели теста: MXID как есть / email / localpart / пусто → админ."""

    def test_mxid_verbatim(self):
        from app.api.matrix_bot import resolve_test_target

        assert (
            resolve_test_target("@x:matrix.mage.ru", admin_email="a@mage.ru", server_name="s")
            == "@x:matrix.mage.ru"
        )

    def test_email_via_convention_lowercase(self):
        from app.api.matrix_bot import resolve_test_target

        assert (
            resolve_test_target(
                "Borzihin.VS@mage.ru", admin_email="a@mage.ru", server_name="matrix.mage.ru"
            )
            == "@borzihin.vs:matrix.mage.ru"
        )

    def test_localpart_appends_server(self):
        from app.api.matrix_bot import resolve_test_target

        assert (
            resolve_test_target("Petrov.SS", admin_email="a@mage.ru", server_name="matrix.mage.ru")
            == "@petrov.ss:matrix.mage.ru"
        )

    def test_empty_falls_back_to_admin_email(self):
        from app.api.matrix_bot import resolve_test_target

        assert (
            resolve_test_target(None, admin_email="admin@mage.ru", server_name="matrix.mage.ru")
            == "@admin:matrix.mage.ru"
        )
        assert (
            resolve_test_target("   ", admin_email="admin@mage.ru", server_name="matrix.mage.ru")
            == "@admin:matrix.mage.ru"
        )
