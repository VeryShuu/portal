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

import uuid
from email import message_from_bytes
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.helpdesk.attachments import _TotalTracker
from app.services.helpdesk.ingress import _ingest_message, poll_mailbox


def _noop_localize_result() -> tuple:
    """Возвращает (html=None, tracker=пустой) — мок результата
    ``_localize_attachments_and_images`` после H-5 (теперь возвращает кортеж)."""
    return (None, _TotalTracker())


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
# poll_done уровень лога: DEBUG при пустом поллинге, INFO при наличии событий
# ---------------------------------------------------------------------------


class _FakeEmptyClient(_FakeClient):
    """IMAP-клиент с пустым ящиком (SEARCH ALL → нет UID'ов)."""

    def __init__(self) -> None:
        super().__init__()
        self.search = AsyncMock(return_value=("OK", [b""]))


@pytest.mark.asyncio
async def test_poll_done_debug_when_mailbox_empty() -> None:
    """Пустой poll (fetched=0, errors=0) — норма для ящика, опрашиваемого каждые
    30с. poll_done должен логироваться на DEBUG, иначе ~95% worker-лога от
    helpdesk — бесполезный шум (инцидент объёма логов 2026-07-29).
    """
    import app.services.helpdesk.ingress as ingress_mod

    db = MagicMock()
    redis = MagicMock()
    debug_calls: list[str] = []
    info_calls: list[str] = []

    with (
        patch.object(ingress_mod, "_make_imap_client", return_value=_FakeEmptyClient()),
        patch.object(ingress_mod, "_decrypt_password", return_value="pw"),
        patch.object(
            ingress_mod.logger,
            "debug",
            side_effect=lambda *a, **k: debug_calls.append(a[0] if a else k.get("event", "")),
        ),
        patch.object(
            ingress_mod.logger,
            "info",
            side_effect=lambda *a, **k: info_calls.append(a[0] if a else k.get("event", "")),
        ),
    ):
        summary = await poll_mailbox(db, redis, settings_row=_settings_row())

    assert summary == {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}
    assert "helpdesk.ingress.poll_done" in debug_calls
    assert "helpdesk.ingress.poll_done" not in info_calls


@pytest.mark.asyncio
async def test_poll_done_info_when_messages_present() -> None:
    """Непустой poll (есть письма или ошибки) — реальное событие, остаётся на INFO."""
    import app.services.helpdesk.ingress as ingress_mod

    db = MagicMock()
    redis = MagicMock()
    debug_calls: list[str] = []
    info_calls: list[str] = []

    async def _process_uid(db_arg, redis_arg, client, uid, *, settings_row, summary):
        summary["created"] += 1

    with (
        patch.object(ingress_mod, "_make_imap_client", return_value=_FakeClient()),
        patch.object(ingress_mod, "_decrypt_password", return_value="pw"),
        patch.object(ingress_mod, "_process_uid", side_effect=_process_uid),
        patch.object(
            ingress_mod.logger,
            "debug",
            side_effect=lambda *a, **k: debug_calls.append(a[0] if a else k.get("event", "")),
        ),
        patch.object(
            ingress_mod.logger,
            "info",
            side_effect=lambda *a, **k: info_calls.append(a[0] if a else k.get("event", "")),
        ),
    ):
        summary = await poll_mailbox(db, redis, settings_row=_settings_row())

    assert summary["created"] == 2  # _FakeClient.search → UIDs "1 2"
    assert "helpdesk.ingress.poll_done" in info_calls
    assert "helpdesk.ingress.poll_done" not in debug_calls


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


def _new_ticket_msg() -> Any:
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
    # _localize_remote_post_commit мокаем — post-commit шаг H-2 не нужен в tx-тесте.
    with (
        patch(
            "app.services.helpdesk.ingress._localize_attachments_and_images",
            new=AsyncMock(return_value=_noop_localize_result()),
        ),
        patch(
            "app.services.helpdesk.ingress._localize_remote_post_commit",
            new=AsyncMock(),
        ),
        patch("app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply_email", new=AsyncMock()),
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
            new=AsyncMock(return_value=_noop_localize_result()),
        ),
        patch(
            "app.services.helpdesk.ingress._localize_remote_post_commit",
            new=AsyncMock(),
        ),
        patch("app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply_email", new=AsyncMock()),
        patch("app.services.helpdesk.ingress._write_log", new=AsyncMock()) as wl,
    ):
        await _ingest_message(db, redis, _new_ticket_msg(), "<abc@x>", settings_row, summary)

    wl.assert_not_awaited()


# ---------------------------------------------------------------------------
# H-2: remote-fetch вне основной транзакции (post-commit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_localizes_remote_post_commit_not_in_transaction() -> None:
    """H-2: remote http(s) картинки локализуются ПОСЛЕ коммита, отдельным шагом.

    Раньше ``_localize_attachments_and_images`` (с медленным httpx-fetch) звался
    между ``flush`` и ``commit`` → DB-транзакция открыта минуты (pool
    exhaustion). Теперь: ``_localize_attachments_and_images`` вызывается с
    ``include_remote=False`` (в транзакции — только cid:+attachments), а
    ``_localize_remote_post_commit`` — после коммита, в отдельной сессии.
    """
    commit_counter: list[int] = []
    db = _ingest_db(commit_counter)
    redis = MagicMock()
    settings_row = _settings_row()
    summary = {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}

    localize_calls: list[bool] = []  # запоминаем include_remote
    post_commit_calls: list[bool] = []

    async def _track_localize(db_arg, *, msg, ticket, message, body_html, include_remote=True):
        localize_calls.append(include_remote)
        return _noop_localize_result()

    async def _track_post_commit(**kwargs):
        post_commit_calls.append(True)

    with (
        patch(
            "app.services.helpdesk.ingress._localize_attachments_and_images",
            side_effect=_track_localize,
        ),
        patch(
            "app.services.helpdesk.ingress._localize_remote_post_commit",
            side_effect=_track_post_commit,
        ),
        patch("app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply_email", new=AsyncMock()),
    ):
        await _ingest_message(db, redis, _new_ticket_msg(), "<abc@x>", settings_row, summary)

    # В транзакции локализация вызвана с include_remote=False (без remote-fetch).
    assert localize_calls == [False], (
        "_localize_attachments_and_images должна зваться с include_remote=False в транзакции"
    )
    # Post-commit шаг remote-локализации вызван ровно 1 раз.
    assert len(post_commit_calls) == 1, (
        "_localize_remote_post_commit должна зваться 1 раз после коммита"
    )


@pytest.mark.asyncio
async def test_post_commit_localize_uses_separate_session() -> None:
    """H-2: ``_localize_remote_post_commit`` открывает новую сессию, не
    использует основную (коммит основной уже прошёл — remote-fetch изолирован)."""
    from app.services.helpdesk.ingress import _localize_remote_post_commit

    # HTML с remote-картинкой → функция дойдёт до открытия AsyncSessionLocal.
    body_html = '<img src="https://example.com/a.png">'

    # Мокаем AsyncSessionLocal как фабрику контекст-менеджеров, где session.get
    # возвращает None → ранний возврат после открытия сессии (без БД-операций).
    fake_session = MagicMock()
    fake_session.get = AsyncMock(return_value=None)
    fake_session.commit = AsyncMock()

    class _FakeCM:
        async def __aenter__(self) -> MagicMock:
            return fake_session

        async def __aexit__(self, *exc: object) -> bool:
            return False

    with (
        patch(
            "app.services.helpdesk.email_images.find_img_sources",
            return_value=["https://example.com/a.png"],
        ),
        patch("app.core.database.AsyncSessionLocal", return_value=_FakeCM()),
    ):
        await _localize_remote_post_commit(
            ticket_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            message_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            body_html=body_html,
        )

    # AsyncSessionLocal вызывался — функция открывает свою сессию, а не
    # использует основную (коммит которой уже прошёл).
    fake_session.get.assert_awaited()


@pytest.mark.asyncio
async def test_post_commit_localize_skips_when_no_remote_images() -> None:
    """H-2: если remote-картинок нет — сессия вообще не открывается (ранний выход)."""
    from app.services.helpdesk.ingress import _localize_remote_post_commit

    # Только inline cid: и обычные src — remote-fetch не нужен.
    body_html = '<img src="cid:logo"><img src="/local/x.png">'

    with patch("app.core.database.AsyncSessionLocal") as session_factory:
        await _localize_remote_post_commit(
            ticket_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            message_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            body_html=body_html,
        )

    session_factory.assert_not_called()


# ---------------------------------------------------------------------------
# H-5: cleanup файлов-сирот при rollback транзакции
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_cleans_up_files_on_commit_failure() -> None:
    """H-5: при ошибке коммита файлы, записанные в FS, удаляются.

    Раньше: ``save_image_bytes`` пишет файл → ``flush`` → если commit падает,
    файл остаётся без DB-строки. identity ``ticket.number`` уже потрачен и не
    переиспользуется → папка ``TKT-{n}`` течёт. Теперь ``_localize_*`` возвращает
    tracker путей, а ``_ingest_message`` при rollback вызывает cleanup."""
    from pathlib import Path

    from app.services.helpdesk.attachments import _TotalTracker

    commit_counter: list[int] = []
    db = _ingest_db(commit_counter)
    # Симулируем падение commit.
    db.commit = AsyncMock(side_effect=RuntimeError("db connection lost"))
    db.rollback = AsyncMock()
    redis = MagicMock()
    settings_row = _settings_row()
    summary = {"fetched": 0, "created": 0, "appended": 0, "skipped": 0, "errors": 0}

    # Tracker с записанным файлом (симуляция save_image_bytes).
    tracker = _TotalTracker()
    fake_path = Path("/data/helpdesk/TKT-123/orphan_file.png")
    tracker.record(fake_path)

    cleanup_called: list[bool] = []

    def _track_cleanup(t):
        cleanup_called.append(True)
        assert t is tracker

    with (
        patch(
            "app.services.helpdesk.ingress._localize_attachments_and_images",
            new=AsyncMock(return_value=(None, tracker)),
        ),
        patch(
            "app.services.helpdesk.ingress._localize_remote_post_commit",
            new=AsyncMock(),
        ),
        patch("app.services.helpdesk.ingress.cleanup_recorded_files", side_effect=_track_cleanup),
        patch("app.services.helpdesk.notifications.notify_ticket_created", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply", new=AsyncMock()),
        patch("app.services.helpdesk.notifications.notify_requester_reply_email", new=AsyncMock()),
        pytest.raises(RuntimeError, match="db connection lost"),
    ):
        await _ingest_message(db, redis, _new_ticket_msg(), "<abc@x>", settings_row, summary)

    # Rollback выполнен.
    db.rollback.assert_awaited_once()
    # Cleanup вызван с тем же tracker.
    assert cleanup_called == [True]


@pytest.mark.asyncio
async def test_cleanup_recorded_files_removes_files() -> None:
    """Юнит-тест ``cleanup_recorded_files``: удаляет зарегистрированные пути."""
    import tempfile
    from pathlib import Path

    from app.services.helpdesk.attachments import _TotalTracker, cleanup_recorded_files

    # Создаём временные файлы.
    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "a.png"
        p2 = Path(tmp) / "b.png"
        p1.write_bytes(b"x")
        p2.write_bytes(b"y")
        assert p1.exists() and p2.exists()

        tracker = _TotalTracker()
        tracker.record(p1)
        tracker.record(p2)

        cleanup_recorded_files(tracker)

        assert not p1.exists()
        assert not p2.exists()


@pytest.mark.asyncio
async def test_cleanup_recorded_files_none_tracker_noop() -> None:
    """``cleanup_recorded_files(None)`` — no-op, не падает."""
    from app.services.helpdesk.attachments import cleanup_recorded_files

    cleanup_recorded_files(None)  # не должно поднимать
