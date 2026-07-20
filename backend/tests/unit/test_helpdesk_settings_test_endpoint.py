"""Unit-тесты ``POST /settings/mailbox/test`` (H-9).

До правки endpoint возвращал ``{"ok": False, "error": str(exc)}`` наружу.
``probe_imap_connection`` логинится реальным паролем; aioimaplib (и другие
IMAP-библиотеки) в исключения иногда включает выполненную команду, где
фигурирует пароль (``C: A1 LOGIN <user> <password>``). Defense-in-depth: даже
AdminDep — маскируем, чтобы креды не утекли в HTTP-ответ и прокси/access-логи.

После правки: ``{"ok": False, "error": "IMAP connection failed (see server
logs for details)"}``. Полный traceback остаётся в server-log через
``logger.exception``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.api.helpdesk.settings import (
    test_mailbox_connection as mailbox_test_endpoint,
)
from app.models.user import User


class _UserFactory(SQLAlchemyFactory[User]):
    """In-memory ``User`` через polyfactory — типизированный объект вместо
    ``SimpleNamespace`` (mypy строгий на ``tests/`` scope)."""

    __model__ = User
    __set_relationships__ = False


def _admin() -> User:
    return _UserFactory.build(id=uuid.uuid4(), email="admin@portal.local", role="admin")


def _row() -> SimpleNamespace:
    """Mailbox-settings stub с зашифрованным паролем."""
    return SimpleNamespace(
        imap_host="imap.company.local",
        imap_port=993,
        imap_username="support@company.local",
        imap_password_enc="enc-secret",
        imap_use_ssl=True,
        imap_folder="INBOX",
    )


def _make_db(row: SimpleNamespace | None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
class TestMailboxTestEndpointMasksException:
    async def test_exception_message_not_leaked(self) -> None:
        """H-9: голый ``str(exc)`` не отдаётся наружу. ``probe_imap_connection``
        поднял исключение с командой и паролем — endpoint возвращает
        generic-сообщение без утечки."""
        db = _make_db(_row())
        exc_with_secret = RuntimeError(
            "aioimaplib command failed: C: A1 LOGIN support@company.local SECRET-PASSWORD-123"
        )

        with (
            patch(
                "app.api.helpdesk.settings.decrypt_secret",
                return_value="SECRET-PASSWORD-123",
            ),
            patch(
                "app.services.helpdesk.ingress.probe_imap_connection",
                new=AsyncMock(side_effect=exc_with_secret),
            ),
        ):
            result = await mailbox_test_endpoint(_admin(), db)

        assert result["ok"] is False
        # Generic-сообщение без деталей исключения.
        assert "SECRET-PASSWORD-123" not in result["error"]
        assert "LOGIN" not in result["error"]
        assert "see server logs" in result["error"]

    async def test_ok_response_preserved(self) -> None:
        """Успешный probe → ``{ok: True, detail: ...}`` как и раньше."""
        db = _make_db(_row())

        with (
            patch("app.api.helpdesk.settings.decrypt_secret", return_value="pw"),
            patch(
                "app.services.helpdesk.ingress.probe_imap_connection",
                new=AsyncMock(return_value=(True, "INBOX selected (5 messages)")),
            ),
        ):
            result = await mailbox_test_endpoint(_admin(), db)

        assert result["ok"] is True
        assert "INBOX" in result["detail"]

    async def test_404_when_not_configured(self) -> None:
        """Singleton не создан → 404 (без probe, без утечки)."""
        from fastapi import HTTPException

        db = _make_db(None)
        with pytest.raises(HTTPException) as exc_info:
            await mailbox_test_endpoint(_admin(), db)
        assert exc_info.value.status_code == 404
