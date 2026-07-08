"""Unit-тесты транзакционной дисциплины helpdesk ingress.

Два CRITICAL-бага, которые здесь ловятся:

1. **Session poisoning** — при исключении из ``_process_uid`` нет ``db.rollback()``:
   IntegrityError переводит AsyncSession в failed-state, и все последующие UID
   батча падают с PendingRollbackError. Один битый UID ронял весь батч.

2. **Split-commit / идемпотентность** — бизнес-коммит сообщения и запись
   ``helpdesk_email_log`` были в разных транзакциях. Сбой между ними → письмо
   создано, но не залогировано → повторная обработка / дубль.

Эти баги не ловились integration-тестами (savepoint-модель маскирует).
Здесь — мок-сессия с подсчётом ``commit``/``rollback`` вызовов.
"""

from __future__ import annotations

from email import message_from_bytes
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.ingress import _ingest_message, poll_mailbox


class _FakeClient:
    """Минимальный fake aioimaplib-клиента для poll_mailbox."""

    def __init__(self) -> None:
        self.search = AsyncMock(return_value=("OK", [b"1 2"]))
        self.fetch = AsyncMock(return_value=("OK", [b"1 FETCH (RFC822 {4}", b"DATA", b")"]))
        self.store = AsyncMock(return_value=("OK", [b"1"]))
        self.expunge = AsyncMock(return_value=("OK", []))
        self.logout = AsyncMock(return_value=("OK", []))
        self.wait_hello_from_server = AsyncMock(return_value=None)
        self.login = AsyncMock(return_value=("OK", [b"LOGIN ok"]))
        self.select = AsyncMock(return_value=("OK", [b"1"]))


def _settings_row() -> MagicMock:
    s = MagicMock()
    s.imap_host = "h"
    s.imap_port = 993
    s.imap_use_ssl = True
    s.imap_username = "u"
    s.imap_password_enc = "enc"
    s.imap_folder = "INBOX"
    s.support_address = "support@example.com"
    s.support_reply_to = None
    s.poll_interval_seconds = 60
    s.delete_after_fetch = False
    return s


@pytest.mark.asyncio
async def test_poll_rollback_on_uid_error_continues_batch() -> None:
    """Session poisoning: один битый UID не должен ронять остальные.

    ``_process_uid`` поднимает исключение на первом UID → poll_mailbox ловит,
    вызывает ``db.rollback()`` и продолжает второй UID. Без rollback сессия
    осталась бы в failed-state, и второй _process_uid упал бы.
    """
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    redis = MagicMock()

    call_log: list[str] = []

    async def _process_uid(db_arg, redis_arg, client, uid, *, settings_row, summary):
        call_log.append(uid)
        if uid == "1":
            raise RuntimeError("boom on first uid")

    with (
        patch("app.services.helpdesk.ingress._make_imap_client", return_value=_FakeClient()),
        patch("app.services.helpdesk.ingress._decrypt_password", return_value="pw"),
        patch("app.services.helpdesk.ingress._process_uid", side_effect=_process_uid),
    ):
        summary = await poll_mailbox(db, redis, settings_row=_settings_row())

    # Оба UID обработаны (батч не прервался).
    assert call_log == ["1", "2"]
    # Rollback вызван для сброса failed-state после исключения.
    db.rollback.assert_awaited_once()
    assert summary["errors"] == 1


@pytest.mark.asyncio
async def test_poll_does_not_rollback_on_success() -> None:
    """Успешная обработка UID не должна вызывать rollback."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    redis = MagicMock()

    async def _process_uid(db_arg, redis_arg, client, uid, *, settings_row, summary):
        pass  # успех, без исключений

    with (
        patch("app.services.helpdesk.ingress._make_imap_client", return_value=_FakeClient()),
        patch("app.services.helpdesk.ingress._decrypt_password", return_value="pw"),
        patch("app.services.helpdesk.ingress._process_uid", side_effect=_process_uid),
    ):
        await poll_mailbox(db, redis, settings_row=_settings_row())

    db.rollback.assert_not_awaited()
    db.commit.assert_not_awaited()  # poll_mailbox сам не коммитит — _process_uid/ingest


# ---------------------------------------------------------------------------
# Split-commit / идемпотентность: лог в той же транзакции, что и сообщение
# ---------------------------------------------------------------------------


def _empty_result() -> MagicMock:
    """Имитация пустого ``Result``: ``.scalars().first()/.one_or_none()`` → None."""
    scalars = MagicMock()
    scalars.first.return_value = None
    scalars.one_or_none.return_value = None
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _ingest_db(commit_counter: list[int]) -> MagicMock:
    """Мок AsyncSession для ``_ingest_message``.

    ``commit`` записывает вызов в ``commit_counter`` (позволяет точно
    посчитать число коммитов). Все execute возвращают пустые результаты
    (нет существующего тикета → создаётся новый, нет пользователя → гость).
    """
    db = MagicMock()
    db.execute = AsyncMock(return_value=_empty_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    async def _commit():
        commit_counter.append(1)

    db.commit = AsyncMock(side_effect=_commit)
    return db


def _new_ticket_msg() -> object:
    """Минимальное RFC822-письмо без References → новый тикет."""
    raw = (
        b"From: sender@example.com\r\n"
        b"Subject: Hello\r\n"
        b"Message-ID: <abc@x>\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Body text"
    )
    return message_from_bytes(raw)


@pytest.mark.asyncio
async def test_ingest_commits_once_with_log_in_same_transaction() -> None:
    """Split-commit: при успешном ingest ``db.commit`` вызывается ровно 1 раз.

    Раньше: commit сообщения (:486) + отдельный commit в ``_write_log`` (:488) = 2
    коммита. Сбой между ними → письмо создано, лог не записан → дубль при
    повторной обработке. Теперь лог добавляется в сессию до единого commit.
    """
    commit_counter: list[int] = []
    db = _ingest_db(commit_counter)
    redis = MagicMock()
    settings_row = _settings_row()
    summary = {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}

    # Локализация и уведомления — no-op, чтобы изолировать транзакционную логику.
    # notify_* импортируются внутри _ingest_message из app.services.helpdesk.notifications.
    with (
        patch(
            "app.services.helpdesk.ingress._localize_attachments_and_images",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()
        ),
        patch(
            "app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()
        ),
    ):
        await _ingest_message(db, redis, _new_ticket_msg(), "<abc@x>", settings_row, summary)

    assert len(commit_counter) == 1, "ingest должен делать ровно 1 commit (бизнес+лог)"
    assert summary["created"] == 1
    # Проверим, что HelpdeskEmailLog добавлен в сессию (а не через отдельный _write_log).
    added_types = [str(a) for a in db.add.call_args_list]
    assert any("HelpdeskEmailLog" in t for t in added_types), (
        "лог должен добавляться в сессию, а не отдельным commit'ом"
    )


@pytest.mark.asyncio
async def test_ingest_does_not_call_write_log_separately() -> None:
    """``_write_log`` не должен вызываться из ``_ingest_message`` (он писал бы
    отдельный commit после бизнес-коммита). Лог добавляется в сессию напрямую."""
    commit_counter: list[int] = []
    db = _ingest_db(commit_counter)
    redis = MagicMock()
    settings_row = _settings_row()
    summary = {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}

    with (
        patch(
            "app.services.helpdesk.ingress._localize_attachments_and_images",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()
        ),
        patch(
            "app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()
        ),
        patch("app.services.helpdesk.ingress._write_log", new=AsyncMock()) as wl,
    ):
        await _ingest_message(db, redis, _new_ticket_msg(), "<abc@x>", settings_row, summary)

    wl.assert_not_awaited()
