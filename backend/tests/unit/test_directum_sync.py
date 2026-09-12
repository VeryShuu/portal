"""Unit-тесты оркестрации прогона Directum (:mod:`app.services.directum.sync`)
и триажа матчера (:mod:`app.services.directum.matcher`).

Все внешние зависимости (OData-fetch, матчер, outbox-enqueue, matrix-settings)
подменяются — тестируется чистая логика: группировка, opt-in-гейт, статусы,
отчёт, дедуп-семантика «каждый прогон».
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.directum import DirectumSettings
from app.services.directum import sync
from app.services.directum.matcher import Ambiguous, Matched, Unmatched, match_performer
from app.services.directum.odata import DirectumApiError, OverdueAssignment

_MOSCOW = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=_MOSCOW)


def _settings(**over) -> DirectumSettings:
    values = dict(
        id=1,
        enabled=True,
        base_url="https://sed.test/odata",
        auth_username="PDC1\\svc",
        auth_password_enc="enc",
        overdue_run_hours=[10],
        expected_interval_days=2,
        notify_emails=None,
        overdue_enabled=True,
    )
    values.update(over)
    return DirectumSettings(**values)


def _task(row_id: str, name: str, days_overdue: int = 5) -> OverdueAssignment:
    return OverdueAssignment(
        id=row_id,
        subject=f"Задача {row_id}",
        deadline=NOW - timedelta(days=days_overdue),
        performer_name=name,
    )


def _user(*, opt_in: bool = True, email: str = "ivanov.ii@mage.ru") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        full_name="Иванов Иван Иванович",
        preferences={"chat_notifications_enabled": opt_in},
        department="IT",
    )


def _matrix_ready_row() -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        access_token_enc="enc",
        homeserver_url="https://matrix.mage.ru",
        server_name="matrix.mage.ru",
        bot_user_id="@portal-bot:matrix.mage.ru",
    )


def _make_db() -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


async def _run_sync(
    *,
    settings: DirectumSettings,
    tasks: list[OverdueAssignment],
    match_results: dict[str, object] | None = None,
    matrix_row: SimpleNamespace | None = None,
    report_emails: list[str] | None = None,
) -> tuple[object, MagicMock, MagicMock]:
    """Прогонить sync с моками; вернуть (run, messenger_enqueue, email_enqueue)."""
    match_results = match_results or {}
    messenger_mock = AsyncMock()
    email_mock = AsyncMock()
    # db.add кладёт настоящий DirectumRun — возвращаем его из мока для инспекции.
    added: list = []

    def _add(obj):
        added.append(obj)

    db = _make_db()
    db.add = _add

    async def _fake_match(_db, fio: str):
        if fio in match_results:
            result = match_results[fio]
            if isinstance(result, Exception):
                raise result
            return result
        from app.services.directum.matcher import Matched

        return Matched(user=_user())  # type: ignore[arg-type]  # SimpleNamespace-заглушка

    with (
        patch.object(sync, "load_directum_settings", AsyncMock(return_value=settings)),
        patch.object(sync, "decrypt_secret", MagicMock(return_value="pw")),
        patch.object(sync, "fetch_overdue_assignments", AsyncMock(return_value=tasks)),
        patch.object(sync, "match_performer", side_effect=_fake_match),
        patch.object(sync, "_load_matrix_settings", AsyncMock(return_value=matrix_row)),
        patch.object(sync, "enqueue_messenger_message", messenger_mock),
        patch.object(sync, "enqueue_outbox_email", email_mock),
        patch.object(
            sync, "get_report_emails", AsyncMock(return_value=report_emails or ["boss@mage.ru"])
        ),
    ):
        run = await sync.run_directum_sync(db, triggered_by="cron")

    return run, messenger_mock, email_mock


class TestRunDirectumSync:
    async def test_not_configured_raises(self):
        db = _make_db()
        with (
            patch.object(
                sync,
                "load_directum_settings",
                AsyncMock(return_value=_settings(auth_password_enc=None)),
            ),
            pytest.raises(RuntimeError, match="not configured"),
        ):
            await sync.run_directum_sync(db)
        db.commit.assert_not_awaited()

    async def test_fetch_failure_creates_failed_run_and_alerts(self):
        settings = _settings()
        email_mock = AsyncMock()
        db = _make_db()
        added: list = []
        db.add = added.append
        with (
            patch.object(sync, "load_directum_settings", AsyncMock(return_value=settings)),
            patch.object(sync, "decrypt_secret", MagicMock(return_value="pw")),
            patch.object(
                sync,
                "fetch_overdue_assignments",
                AsyncMock(side_effect=DirectumApiError("HTTP 503", status_code=503)),
            ),
            patch.object(sync, "enqueue_outbox_email", email_mock),
            patch.object(sync, "get_report_emails", AsyncMock(return_value=["boss@mage.ru"])),
        ):
            run = await sync.run_directum_sync(db, triggered_by="cron")

        assert run.status == "failed"
        assert run.report["error_class"] == "transient"
        assert email_mock.await_count == 1  # алерт админам
        db.commit.assert_awaited_once()

    async def test_happy_path_notifies_matched_opted_in(self):
        tasks = [_task("t1", "Иванов Иван Иванович"), _task("t2", "Иванов Иван Иванович")]
        run, messenger_mock, email_mock = await _run_sync(
            settings=_settings(),
            tasks=tasks,
            match_results={"Иванов Иван Иванович": Matched(user=_user())},
            matrix_row=_matrix_ready_row(),
        )
        assert run.status == "success"
        assert run.tasks_total == 2
        assert run.performers_total == 1
        assert run.users_notified == 1
        # Дайджест — один на сотрудника (обе задачи в одном сообщении).
        assert messenger_mock.await_count == 1
        kwargs = messenger_mock.await_args.kwargs
        assert kwargs["provider"] == "matrix"
        assert kwargs["chat_id"] == "@ivanov.ii:matrix.mage.ru"
        assert "t1" in kwargs["text"] or "Задача t1" in kwargs["text"]
        assert kwargs["related_resource_type"] == "directum_run"
        assert email_mock.await_count == 1  # сводка

    async def test_opt_out_user_skipped_and_reported(self):
        run, messenger_mock, _ = await _run_sync(
            settings=_settings(),
            tasks=[_task("t1", "Петров Пётр Петрович")],
            match_results={"Петров Пётр Петрович": Matched(user=_user(opt_in=False))},
            matrix_row=_matrix_ready_row(),
        )
        assert run.status == "success"  # opt-out — штатное поведение, не partial
        assert run.users_skipped_opt_in == 1
        assert run.users_notified == 0
        messenger_mock.assert_not_awaited()
        assert run.report["skipped_opt_in"][0]["fio"] == "Петров Пётр Петрович"

    async def test_matrix_not_ready_makes_partial(self):
        run, messenger_mock, _ = await _run_sync(
            settings=_settings(),
            tasks=[_task("t1", "Иванов Иван Иванович")],
            matrix_row=None,  # бот не настроен
        )
        assert run.status == "partial"
        assert run.users_notified == 0
        messenger_mock.assert_not_awaited()
        assert run.report["matrix_disabled"] is True
        assert run.report["skipped_matrix_disabled"] == ["Иванов Иван Иванович"]

    async def test_unmatched_and_ambiguous_reported(self):
        run, _, _ = await _run_sync(
            settings=_settings(),
            tasks=[
                _task("t1", "Капитан судна Н.Трубятчинский"),
                _task("t2", "Сидоров Сидор Сидорович"),
            ],
            match_results={
                "Капитан судна Н.Трубятчинский": Unmatched(),
                "Сидоров Сидор Сидорович": Ambiguous(
                    candidates=[_user(), _user(email="other@mage.ru")]
                ),
            },
            matrix_row=_matrix_ready_row(),
        )
        assert run.status == "success"
        assert run.users_unmatched == 1
        assert run.users_ambiguous == 1
        assert len(run.report["ambiguous"][0]["candidates"]) == 2

    async def test_empty_performer_name_goes_to_unmatched(self):
        run, _, _ = await _run_sync(
            settings=_settings(),
            tasks=[_task("t1", "")],
            matrix_row=_matrix_ready_row(),
        )
        assert run.users_unmatched == 1
        assert run.report["unmatched"][0]["fio"] == "(исполнитель не указан)"

    async def test_zero_tasks_success_without_email(self):
        run, _, email_mock = await _run_sync(
            settings=_settings(), tasks=[], matrix_row=_matrix_ready_row()
        )
        assert run.status == "success"
        assert run.tasks_total == 0
        email_mock.assert_not_awaited()  # пустой прогон не спамит письмом

    async def test_performer_error_counted_run_continues(self):
        run, _, _ = await _run_sync(
            settings=_settings(),
            tasks=[_task("t1", "Беда Бедович"), _task("t2", "Иванов Иван Иванович")],
            match_results={"Беда Бедович": RuntimeError("db boom")},
            matrix_row=_matrix_ready_row(),
        )
        assert run.errors == 1
        assert run.status == "partial"
        assert run.users_notified == 1  # второй исполнитель обработан

    async def test_every_run_renotifies(self):
        """Семантика «каждый прогон»: одинаковая выборка дважды = два enqueue."""
        for _ in range(2):
            _, messenger_mock, _ = await _run_sync(
                settings=_settings(),
                tasks=[_task("t1", "Иванов Иван Иванович")],
                matrix_row=_matrix_ready_row(),
            )
            assert messenger_mock.await_count == 1


class TestDirectumConfigured:
    def test_full_credentials(self):
        assert sync.directum_configured(_settings()) is True

    def test_missing_password(self):
        assert sync.directum_configured(_settings(auth_password_enc=None)) is False

    def test_missing_username(self):
        assert sync.directum_configured(_settings(auth_username=None)) is False


class TestMatcherTriage:
    async def test_exact_single_match(self):
        user = _user()
        with (
            patch(
                "app.services.directum.matcher.find_by_full_name_exact",
                AsyncMock(return_value=[user]),
            ) as exact_mock,
            patch("app.services.directum.matcher.find_by_full_name_words") as words_mock,
        ):
            result = await match_performer(MagicMock(), "Иванов Иван Иванович")
        assert isinstance(result, Matched)
        assert result.user is user
        exact_mock.assert_awaited_once()
        words_mock.assert_not_awaited()  # точного совпадения достаточно

    async def test_exact_multiple_is_ambiguous(self):
        users = [_user(), _user(email="other@mage.ru")]
        with patch(
            "app.services.directum.matcher.find_by_full_name_exact",
            AsyncMock(return_value=users),
        ):
            result = await match_performer(MagicMock(), "Однофамилец")
        assert isinstance(result, Ambiguous)
        assert len(result.candidates) == 2

    async def test_words_fallback_single(self):
        user = _user()
        with (
            patch(
                "app.services.directum.matcher.find_by_full_name_exact",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.directum.matcher.find_by_full_name_words",
                AsyncMock(return_value=[user]),
            ),
        ):
            result = await match_performer(MagicMock(), "Иванов Иван")
        assert isinstance(result, Matched)

    async def test_nothing_found_unmatched(self):
        with (
            patch(
                "app.services.directum.matcher.find_by_full_name_exact",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.directum.matcher.find_by_full_name_words",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await match_performer(MagicMock(), "Неизвестный Человек")
        assert isinstance(result, Unmatched)
