"""Unit-тесты для app/worker/tasks/notifications.py.

Покрытие:
- _esc: экранирование HTML и кавычек.
- _get_smtp_config: файл отсутствует → дефолт; файл валидный → значения; файл невалидный → дефолт.
- _build_news_email_html / _build_suggestion_email_html: экранирование, обе ветки action.
- send_email_notification: успешный путь, конфигурация TLS/STARTTLS/auth, ошибка smtp → re-raise.
- notify_news_published: фильтрация по departments/roles, swallow per-recipient errors.
- notify_suggestion_reviewed_email: правильный subject для approve/reject.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks import notifications as nt


class TestEsc:
    def test_escapes_html(self):
        assert nt._esc("<script>") == "&lt;script&gt;"

    def test_escapes_quotes(self):
        assert "&quot;" in nt._esc('"hi"')

    def test_none_returns_empty(self):
        assert nt._esc(None) == ""


class TestGetSmtpConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        fake_path = tmp_path / "nonexistent.json"
        with patch("app.worker.tasks.email_utils.EMAIL_SETTINGS_PATH", fake_path):
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
        with patch("app.worker.tasks.email_utils.EMAIL_SETTINGS_PATH", f):
            from app.worker.tasks.email_utils import load_smtp_config
            cfg = load_smtp_config()
        assert cfg["host"] == "smtp.local"
        assert cfg["port"] == 587
        assert cfg["use_tls"] is True

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        f = tmp_path / "email-settings.json"
        f.write_text("not-json", "utf-8")
        with patch("app.worker.tasks.email_utils.EMAIL_SETTINGS_PATH", f):
            from app.worker.tasks.email_utils import load_smtp_config
            cfg = load_smtp_config()
        assert cfg["host"] == ""


class TestBuildNewsEmailHtml:
    def test_escapes_title_and_link(self):
        html, text = nt._build_news_email_html("<bad>", "http://x?<a>", "Portal&Co")
        assert "&lt;bad&gt;" in html
        assert "Portal&amp;Co" in html
        assert "http://x?&lt;a&gt;" in html
        assert text.startswith("Portal&Co")

    def test_text_contains_url(self):
        _, text = nt._build_news_email_html("t", "http://link", "Portal")
        assert "http://link" in text


class TestBuildSuggestionEmailHtml:
    def test_approve_renders_green(self):
        html, text = nt._build_suggestion_email_html("Title", "http://l", "approve", "Portal")
        assert "одобрена" in html
        assert "одобрена" in text
        assert "#27ae60" in html

    def test_reject_renders_red(self):
        html, text = nt._build_suggestion_email_html("Title", "http://l", "reject", "Portal")
        assert "отклонена" in html
        assert "#c0392b" in html


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
        with patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg), patch(
            "aiosmtplib.send", send_mock
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

        with patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg), patch(
            "aiosmtplib.send", side_effect=_send
        ):
            await nt.send_email_notification(
                {}, to_email="to@x", subject="s", body_html="<b>h</b>"
            )
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
        with patch("app.worker.tasks.notifications.load_smtp_config", return_value=cfg), patch(
            "aiosmtplib.send", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            with pytest.raises(RuntimeError):
                await nt.send_email_notification(
                    {}, to_email="to@x", subject="s", body_html="<b>h</b>"
                )


class TestNotifySuggestionReviewedEmail:
    @pytest.mark.asyncio
    async def test_approve_subject(self):
        enqueue_mock = AsyncMock()
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)
        
        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock()
        db_mock.begin = MagicMock(return_value=begin_mock)
        
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch.object(nt, "load_system_settings", return_value=MagicMock(portal_base_url="http://p"))
        ):
            await nt.notify_suggestion_reviewed_email(
                {},
                author_email="a@x",
                article_id="aid",
                article_title="T",
                action="approve",
            )
        kwargs = enqueue_mock.await_args.kwargs
        assert "одобрена" in kwargs["subject"]
        assert "http://p/kb/articles/aid" in kwargs["body_text"]

    @pytest.mark.asyncio
    async def test_reject_subject(self):
        enqueue_mock = AsyncMock()
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)
        
        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock()
        db_mock.begin = MagicMock(return_value=begin_mock)
        
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch.object(nt, "load_system_settings", return_value=MagicMock(portal_base_url="http://p"))
        ):
            await nt.notify_suggestion_reviewed_email(
                {},
                author_email="a@x",
                article_id="aid",
                article_title="T",
                action="reject",
            )
        kwargs = enqueue_mock.await_args.kwargs
        assert "отклонена" in kwargs["subject"]


class TestNotifyNewsPublished:
    @pytest.mark.asyncio
    async def test_filters_by_department_and_role_and_swallows_per_user_errors(self):
        rows = [
            {"id": "u1", "email": "u1@x", "department": "IT", "role": "user"},
            {"id": "u2", "email": "u2@x", "department": "HR", "role": "user"},
            {"id": "u3", "email": "u3@x", "department": "IT", "role": "admin"},
        ]
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.close = AsyncMock()

        enqueue_mock = AsyncMock(side_effect=[None, RuntimeError("db error")])
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)
        
        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock()
        db_mock.begin = MagicMock(return_value=begin_mock)
        
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch.object(nt, "load_system_settings", return_value=MagicMock(portal_base_url="http://p"))
        ):
            sent = await nt.notify_news_published(
                {},
                news_id="00000000-0000-0000-0000-000000000001",
                news_title="N",
                target_departments=["IT"],
                target_roles=["user"],
            )

        # Только u1 проходит оба фильтра — отправка одна, ошибок нет.
        assert sent == 1
        assert enqueue_mock.await_count == 1
        conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_targets_sends_to_all_subscribers(self):
        rows = [
            {"id": "u1", "email": "u1@x", "department": "A", "role": "r"},
            {"id": "u2", "email": "u2@x", "department": "B", "role": "r"},
        ]
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.close = AsyncMock()
        enqueue_mock = AsyncMock(return_value=None)
        db_mock = AsyncMock()
        db_mock.__aenter__ = AsyncMock(return_value=db_mock)
        db_mock.__aexit__ = AsyncMock(return_value=None)
        
        begin_mock = AsyncMock()
        begin_mock.__aenter__ = AsyncMock()
        begin_mock.__aexit__ = AsyncMock()
        db_mock.begin = MagicMock(return_value=begin_mock)
        
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db_mock)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
            patch("app.core.database.AsyncSessionLocal", return_value=session_cm),
            patch("app.services.email_outbox.enqueue_outbox_email", enqueue_mock),
            patch.object(nt, "load_system_settings", return_value=MagicMock(portal_base_url="http://p"))
        ):
            sent = await nt.notify_news_published(
                {}, news_id="00000000-0000-0000-0000-000000000001", news_title="N"
            )
        assert sent == 2
