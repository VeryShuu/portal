"""Integration tests for helpdesk mailbox settings + module gating (Этап 5).

Проверяет singleton-семантику mailbox-settings (ТЗ §3.6): GET до PUT →
``configured=false``; PUT с паролем → создаёт; PUT без пароля → оставляет
прежний шифр; пароль write-only (только ``imap_password_set``). И гейтинг:
``require_helpdesk_module`` кидает 404 при выключенном модуле.

Авто-skip'ается без ``INTEGRATION_DB=true``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.helpdesk.settings import get_mailbox_settings, put_mailbox_settings
from app.schemas.helpdesk import HelpdeskMailboxSettingsIn

pytestmark = pytest.mark.asyncio


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.rpush = AsyncMock()
    return r


def _payload(**overrides) -> HelpdeskMailboxSettingsIn:
    base = {
        "imap_host": "imap.company.local",
        "imap_username": "support",
        "imap_password": "secret123",
        "support_address": "support@company.local",
    }
    base.update(overrides)
    return HelpdeskMailboxSettingsIn(**base)  # type: ignore[arg-type]


class TestMailboxSingleton:
    async def test_get_before_put_returns_not_configured(self, real_db_session, real_admin):
        out = await get_mailbox_settings(real_admin, real_db_session)
        assert out.configured is False
        assert out.imap_password_set is False

    async def test_put_creates_with_password(self, real_db_session, real_admin):
        out = await put_mailbox_settings(_payload(), real_admin, real_db_session, _redis())
        assert out.configured is True
        assert out.imap_password_set is True
        assert out.imap_host == "imap.company.local"
        assert out.support_address == "support@company.local"

    async def test_put_without_password_keeps_previous(self, real_db_session, real_admin):
        await put_mailbox_settings(
            _payload(imap_password="first"), real_admin, real_db_session, _redis()
        )
        # Обновление без пароля → прежний шифр сохраняется, флаг остаётся True.
        out = await put_mailbox_settings(
            _payload(imap_password=None, imap_host="new.imap.local"),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert out.imap_host == "new.imap.local"
        assert out.imap_password_set is True

    async def test_password_is_write_only(self, real_db_session, real_admin):
        await put_mailbox_settings(
            _payload(imap_password="never-expose"), real_admin, real_db_session, _redis()
        )
        out = await get_mailbox_settings(real_admin, real_db_session)
        # Пароль никогда не возвращается — только признак.
        assert not hasattr(out, "imap_password")
        assert out.imap_password_set is True

    async def test_password_encrypted_at_rest(self, real_db_session, real_admin):
        from sqlalchemy import select

        from app.models.helpdesk import HelpdeskMailboxSettings

        await put_mailbox_settings(
            _payload(imap_password="plaintext-secret"), real_admin, real_db_session, _redis()
        )
        res = await real_db_session.execute(
            select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
        )
        row = res.scalars().one()
        # В БД лежит шифр, не плейнтекст.
        assert "plaintext-secret" not in row.imap_password_enc
        # Расшифровка восстанавливает оригинал.
        from app.core.secret_crypto import decrypt_secret

        assert decrypt_secret(row.imap_password_enc) == "plaintext-secret"


class TestSmtpSettings:
    """SMTP-блок mailbox-settings (миграция 086): собственный исходящий контур.

    Зеркало IMAP-тестов: round-trip полей, write-only пароль, шифр в БД. Все
    поля опциональны (fallback на общий SMTP портала при пустом ``smtp_host``),
    поэтому тесты не требуют SMTP-настроек для прохождения — проверяют только
    персистентность конфигурации.
    """

    async def test_smtp_fields_round_trip(self, real_db_session, real_admin):
        """PUT с SMTP-блоком → GET возвращает те же значения, пароль write-only."""
        out = await put_mailbox_settings(
            _payload(
                smtp_host="smtp.company.local",
                smtp_port=587,
                smtp_username="support",
                smtp_password="smtp-secret",
                smtp_use_tls=False,
                smtp_use_starttls=True,
            ),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert out.smtp_host == "smtp.company.local"
        assert out.smtp_port == 587
        assert out.smtp_username == "support"
        assert out.smtp_use_tls is False
        assert out.smtp_use_starttls is True
        assert out.smtp_password_set is True
        # Пароль не возвращается.
        assert not hasattr(out, "smtp_password")

    async def test_smtp_password_write_only_on_update(self, real_db_session, real_admin):
        """PUT без smtp_password → прежний шифр сохраняется, флаг остаётся True."""
        await put_mailbox_settings(
            _payload(smtp_host="smtp.local", smtp_password="first-pw"),
            real_admin,
            real_db_session,
            _redis(),
        )
        # Обновление IMAP-хоста без SMTP-пароля → SMTP-шифр сохранён.
        out = await put_mailbox_settings(
            _payload(smtp_host="smtp.local", smtp_password=None, imap_host="new.imap.local"),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert out.smtp_host == "smtp.local"
        assert out.smtp_password_set is True

    async def test_smtp_password_encrypted_at_rest(self, real_db_session, real_admin):
        """В БД лежит шифр, не плейнтекст; расшифровка восстанавливает оригинал."""
        from sqlalchemy import select

        from app.models.helpdesk import HelpdeskMailboxSettings

        await put_mailbox_settings(
            _payload(smtp_host="smtp.local", smtp_password="smtp-plaintext"),
            real_admin,
            real_db_session,
            _redis(),
        )
        res = await real_db_session.execute(
            select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
        )
        row = res.scalars().one()
        assert "smtp-plaintext" not in (row.smtp_password_enc or "")
        from app.core.secret_crypto import decrypt_secret

        assert decrypt_secret(row.smtp_password_enc) == "smtp-plaintext"

    async def test_smtp_optional_on_create(self, real_db_session, real_admin):
        """SMTP-блок целиком опционален: PUT без smtp_* → поля None/defaults."""
        out = await put_mailbox_settings(_payload(), real_admin, real_db_session, _redis())
        assert out.smtp_host is None
        assert out.smtp_password_set is False
        assert out.smtp_port == 25  # дефолт схемы

    async def test_smtp_host_stripped_and_nulled(self, real_db_session, real_admin):
        """Пустой/пробельный smtp_host нормализуется к None (fallback-сигнал)."""
        out = await put_mailbox_settings(
            _payload(smtp_host="   "),
            real_admin,
            real_db_session,
            _redis(),
        )
        assert out.smtp_host is None


class TestModuleGate:
    async def test_gate_disabled_when_module_off(self, real_db_session):
        """``require_helpdesk_module`` читает modules.json; модуль выключен по
        умолчанию → 404. Проверяем через прямую загрузку (модуль не включён в
        тестовом modules.json)."""
        from app.api.deps import require_helpdesk_module

        # fake redis, чтобы load_modules_shared взяла default (helpdesk off).
        fake_redis = AsyncMock()
        # get_version возвращает 0 → кэш не валиден → load_modules() из файла
        # (которого в тестовой среде нет → default AllModuleSettings, helpdesk off).
        fake_redis.get = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await require_helpdesk_module(fake_redis)
        assert exc.value.status_code == 404
