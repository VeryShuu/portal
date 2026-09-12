"""Unit-тесты ``probe_smtp_connection`` (``services/helpdesk/smtp.py``, миграция 086).

Проверка соединения для админ-кнопки «Проверить SMTP». Зеркало
``probe_imap_connection``: connect → (STARTTLS) → login → NOOP → quit.

Мокаем ``aiosmtplib.SMTP`` через ``patch`` на модуль aiosmtplib — клиент
создаётся внутри функции, поэтому подменяем сам класс. Покрываем: happy path
(с auth и без), auth-fail, connect-timeout, STARTTLS-ветку.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.smtp import probe_smtp_connection


def _make_mock_client() -> MagicMock:
    """aiosmtplib.SMTP mock: все async-методы — AsyncMock (no-op по умолчанию)."""
    client = MagicMock()
    client.connect = AsyncMock(return_value=(220, "ready"))
    client.starttls = AsyncMock(return_value=(220, "ready"))
    client.login = AsyncMock(return_value=(235, "auth ok"))
    client.noop = AsyncMock(return_value=(250, "ok"))
    client.quit = AsyncMock(return_value=(221, "bye"))
    return client


@pytest.mark.asyncio
class TestProbeSmtpConnection:
    async def test_success_with_auth(self) -> None:
        """Успешное подключение с TLS + кредами → (True, detail с host:port)."""
        client = _make_mock_client()
        with patch("aiosmtplib.SMTP", return_value=client):
            ok, detail = await probe_smtp_connection(
                host="smtp.company.local",
                port=465,
                username="support@company.local",
                password="secret",
                use_tls=True,
                use_starttls=False,
            )
        assert ok is True
        assert "smtp.company.local:465" in detail
        assert "TLS" in detail
        assert "authenticated" in detail
        client.connect.assert_awaited_once()
        client.login.assert_awaited_once()
        client.noop.assert_awaited_once()
        # quit вызывается в finally всегда.
        client.quit.assert_awaited_once()

    async def test_success_starttls_no_auth(self) -> None:
        """Успешное подключение STARTTLS без кред (открытый релей)."""
        client = _make_mock_client()
        with patch("aiosmtplib.SMTP", return_value=client):
            ok, detail = await probe_smtp_connection(
                host="relay.local",
                port=25,
                username="",
                password="",
                use_tls=False,
                use_starttls=True,
            )
        assert ok is True
        assert "STARTTLS" in detail
        assert "no-auth" in detail
        client.starttls.assert_awaited_once()
        # Без кред — login не вызывается.
        client.login.assert_not_called()

    async def test_auth_failure_returns_false(self) -> None:
        """Auth-fail → (False, "тип исключения: сообщение")."""
        import aiosmtplib

        client = _make_mock_client()
        client.login = AsyncMock(side_effect=aiosmtplib.SMTPAuthenticationError(535, "bad creds"))
        with patch("aiosmtplib.SMTP", return_value=client):
            ok, detail = await probe_smtp_connection(
                host="smtp.company.local",
                port=587,
                username="support@company.local",
                password="wrong",
                use_tls=False,
                use_starttls=True,
            )
        assert ok is False
        assert "SMTPAuthenticationError" in detail
        # quit в finally всё равно вызывается.
        client.quit.assert_awaited_once()

    async def test_connect_timeout_returns_false(self) -> None:
        """Connect-timeout → (False, TimeoutError-сообщение), quit не падает."""
        client = _make_mock_client()
        client.connect = AsyncMock(side_effect=TimeoutError("connect timed out"))
        with patch("aiosmtplib.SMTP", return_value=client):
            ok, detail = await probe_smtp_connection(
                host="unreachable.local",
                port=25,
                username="",
                password="",
                use_tls=False,
                use_starttls=False,
            )
        assert ok is False
        assert "TimeoutError" in detail

    async def test_quit_failure_does_not_mask_result(self) -> None:
        """Если quit бросает после успешного noop — результат остаётся (True).

        finally-блок глотает ошибку quit (соединение уже проверено) — она не
        должна маскировать успешный результат probe.
        """
        client = _make_mock_client()
        client.quit = AsyncMock(side_effect=RuntimeError("already closed"))
        with patch("aiosmtplib.SMTP", return_value=client):
            ok, detail = await probe_smtp_connection(
                host="smtp.local",
                port=25,
                username="u",
                password="p",
                use_tls=False,
                use_starttls=False,
            )
        assert ok is True
        assert "smtp.local" in detail
