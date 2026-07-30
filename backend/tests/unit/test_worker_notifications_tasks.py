"""Unit-тесты для app/worker/tasks/notifications.py.

Покрытие:
- _get_smtp_config: файл отсутствует → дефолт; файл валидный → значения; файл невалидный → дефолт.
- send_email_notification: успешный путь, конфигурация TLS/STARTTLS/auth, ошибка smtp → re-raise.
- notify_news_published: делегирование in-app SSE; нет redis → 0; ошибки проглатываются.
- cleanup_notifications: отключение при retention<=0, проброс retention в service, сумма счётчиков.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import notifications as nt


class TestGetSmtpConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        fake_path = tmp_path / "nonexistent.json"
        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", fake_path):
            from app.worker.tasks.email_utils import load_smtp_config

            cfg = load_smtp_config()
        assert cfg["host"] == ""
        assert cfg["port"] == 25
        assert cfg["use_tls"] is False

    def test_valid_file_returns_values(self, tmp_path):
        f = tmp_path / "email-settings.json"
        f.write_text(
            json.dumps(
                {
                    "host": "smtp.local",
                    "port": "587",
                    "from_address": "p@x",
                    "username": "u",
                    "password": "p",
                    "use_tls": True,
                    "use_starttls": False,
                }
            ),
            "utf-8",
        )
        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", f):
            from app.worker.tasks.email_utils import load_smtp_config

            cfg = load_smtp_config()
        assert cfg["host"] == "smtp.local"
        assert cfg["port"] == 587
        assert cfg["use_tls"] is True

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        f = tmp_path / "email-settings.json"
        f.write_text("not-json", "utf-8")
        with patch("app.services.email_settings.EMAIL_SETTINGS_FILE", f):
            from app.worker.tasks.email_utils import load_smtp_config

            cfg = load_smtp_config()
        assert cfg["host"] == ""


class TestSendEmailNotification:
    @pytest.mark.asyncio
    async def test_success_path(self):
        cfg = {
            "host": "h",
            "port": 25,
            "from_address": "from@x",
            "username": "",
            "password": "",
            "use_tls": False,
            "use_starttls": False,
        }
        send_mock = AsyncMock()
        with (
            patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg),
            patch("aiosmtplib.send", send_mock),
        ):
            ok = await nt.send_email_notification(
                {}, to_email="to@x", subject="s", body_html="<b>h</b>", body_text="t"
            )
        assert ok is True
        send_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_tls_starttls_and_auth(self):
        cfg = {
            "host": "h",
            "port": 465,
            "from_address": "",
            "username": "u",
            "password": "p",
            "use_tls": True,
            "use_starttls": True,
        }
        captured: dict = {}

        async def _send(msg, **kwargs):
            captured.update(kwargs)

        with (
            patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg),
            patch("aiosmtplib.send", side_effect=_send),
        ):
            await nt.send_email_notification({}, to_email="to@x", subject="s", body_html="<b>h</b>")
        assert captured["use_tls"] is True
        assert captured["start_tls"] is True
        assert captured["username"] == "u"
        assert captured["password"] == "p"

    @pytest.mark.asyncio
    async def test_smtp_error_reraised(self):
        cfg = {
            "host": "h",
            "port": 25,
            "from_address": "from@x",
            "username": "",
            "password": "",
            "use_tls": False,
            "use_starttls": False,
        }
        with (
            patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg),
            patch("aiosmtplib.send", AsyncMock(side_effect=RuntimeError("boom"))),
            pytest.raises(RuntimeError),
        ):
            await nt.send_email_notification({}, to_email="to@x", subject="s", body_html="<b>h</b>")


class TestNotifyNewsPublished:
    """Автоматических email по новостям нет: задача только триггерит in-app SSE."""

    def _session_cm(self) -> MagicMock:
        db_mock = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)
        return session_cm

    @pytest.mark.asyncio
    async def test_delegates_to_inapp_and_returns_count(self):
        inapp_mock = AsyncMock(return_value=5)
        with (
            patch("app.core.database.AsyncSessionLocal", return_value=self._session_cm()),
            patch("app.services.notifications.notify_users_news_published", inapp_mock),
        ):
            sent = await nt.notify_news_published(
                {"redis": object()},
                news_id="00000000-0000-0000-0000-000000000001",
                news_title="N",
                target_departments=["IT"],
                target_roles=["user"],
            )

        assert sent == 5
        inapp_mock.assert_awaited_once()
        kwargs = inapp_mock.await_args.kwargs
        assert str(kwargs["news_id"]) == "00000000-0000-0000-0000-000000000001"
        assert kwargs["news_title"] == "N"
        assert kwargs["target_departments"] == ["IT"]
        assert kwargs["target_roles"] == ["user"]

    @pytest.mark.asyncio
    async def test_no_redis_returns_zero_without_db(self):
        with patch("app.core.database.AsyncSessionLocal") as session_factory:
            sent = await nt.notify_news_published(
                {}, news_id="00000000-0000-0000-0000-000000000001", news_title="N"
            )
        assert sent == 0
        session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_inapp_errors_and_returns_zero(self):
        with (
            patch("app.core.database.AsyncSessionLocal", return_value=self._session_cm()),
            patch(
                "app.services.notifications.notify_users_news_published",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            sent = await nt.notify_news_published(
                {"redis": object()},
                news_id="00000000-0000-0000-0000-000000000001",
                news_title="N",
            )
        assert sent == 0


class TestCleanupNotifications:
    """Retention-очистка: проброс настроек в service и отключение при 0.

    Патчится по полным путям (``app.core.…``), т.к. ``cleanup_notifications``
    импортирует зависимости ленивно — как ``notify_news_published`` выше.
    """

    def _cfg(self, *, read: int, unread: int) -> SimpleNamespace:
        return SimpleNamespace(
            notifications_read_retention_days=read,
            notifications_unread_retention_days=unread,
        )

    def _session_cm(self) -> MagicMock:
        db_mock = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)
        begin_cm = MagicMock()
        begin_cm.__aenter__ = AsyncMock(return_value=None)
        begin_cm.__aexit__ = AsyncMock(return_value=None)
        db_mock.begin = MagicMock(return_value=begin_cm)
        return session_cm

    @pytest.mark.asyncio
    async def test_disabled_when_both_retentions_le_zero(self):
        cleanup_mock = AsyncMock()
        with (
            patch(
                "app.core.system_config.load_system_settings",
                return_value=self._cfg(read=0, unread=0),
            ),
            patch("app.services.notifications.cleanup_old_notifications", cleanup_mock),
            patch("app.core.database.AsyncSessionLocal") as session_factory,
        ):
            result = await nt.cleanup_notifications({})

        assert result == 0
        cleanup_mock.assert_not_awaited()
        session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_when_read_zero_and_unread_zero_independent(self):
        # read=0 но unread>0 → НЕ отключена, cleanup зовётся с read=0.
        cleanup_mock = AsyncMock(return_value={"read_deleted": 0, "unread_deleted": 3})
        with (
            patch(
                "app.core.system_config.load_system_settings",
                return_value=self._cfg(read=0, unread=90),
            ),
            patch("app.services.notifications.cleanup_old_notifications", cleanup_mock),
            patch("app.core.database.AsyncSessionLocal", return_value=self._session_cm()),
        ):
            result = await nt.cleanup_notifications({})

        assert result == 3
        cleanup_mock.assert_awaited_once()
        kwargs = cleanup_mock.await_args.kwargs
        assert kwargs["read_retention_days"] == 0
        assert kwargs["unread_retention_days"] == 90

    @pytest.mark.asyncio
    async def test_sums_read_and_unread_deleted(self):
        cleanup_mock = AsyncMock(return_value={"read_deleted": 12, "unread_deleted": 5})
        with (
            patch(
                "app.core.system_config.load_system_settings",
                return_value=self._cfg(read=30, unread=90),
            ),
            patch("app.services.notifications.cleanup_old_notifications", cleanup_mock),
            patch("app.core.database.AsyncSessionLocal", return_value=self._session_cm()),
        ):
            result = await nt.cleanup_notifications({})

        assert result == 17
        cleanup_mock.assert_awaited_once_with(
            cleanup_mock.await_args.args[0],
            read_retention_days=30,
            unread_retention_days=90,
        )
