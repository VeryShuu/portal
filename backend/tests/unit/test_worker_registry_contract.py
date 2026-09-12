"""Контрактный тест полного ARQ-реестра воркера (аудит тестирования 2026-08-23, P1).

Прежняя защита ограничивалась двумя meetings-функциями
(test_meetings_worker_settings.py): удаление из WorkerSettings функций вроде
process_email_outbox / poll_helpdesk_mailbox / process_messenger_outbox
оставалось зелёным — app/worker/main.py целиком исключён из coverage
(pyproject.toml §[tool.coverage.run] omit).

Снапшот-контракт: любое изменение реестра (добавление/удаление задачи или
cron'а) обязано обновить EXPECTED_* — случайная потеря фоновой задачи
ловится сразу, а не по «почему письма не уходят» на проде.

Контрпример-валидация: убрать любую строку из WorkerSettings.functions /
WorkerSettings.cron_jobs → соответствующий тест падает.
"""

from __future__ import annotations


def _registered_function_names() -> set[str]:
    """Имена зарегистрированных функций в едином виде.

    ``track_arq_job``-обёртки сохраняют ``__name__`` (functools.wraps), а
    ``func(...)`` возвращает arq-объект ``Function`` с атрибутом ``name``.
    """
    from app.worker.main import WorkerSettings

    names: set[str] = set()
    for entry in WorkerSettings.functions:
        name = getattr(entry, "name", None) or getattr(entry, "__name__", None)
        if name is None:  # pragma: no cover — защитная сетка при смене API arq
            raise AssertionError(f"Не удалось извлечь имя задачи: {entry!r}")
        names.add(name)
    return names


def _registered_cron_names() -> set[str]:
    from app.worker.main import WorkerSettings

    names: set[str] = set()
    for job in WorkerSettings.cron_jobs:
        coroutine = getattr(job, "coroutine", None)
        name = getattr(coroutine, "__name__", None) or str(coroutine)
        names.add(name)
    return names


# Снапшот WorkerSettings.functions (порядок не важен, важен состав).
# Обновляется ВРУЧНУЮ вместе с реестром — это и есть контракт.
EXPECTED_FUNCTIONS = {
    "startup_sync_nc_folders",
    "sync_users_from_keycloak",
    "close_expired_polls",
    "send_email_notification",
    "notify_news_published",
    "cleanup_notifications",
    "process_photo_upload",
    "cleanup_deleted_photos",
    "generate_folder_zip",
    "cleanup_zip_jobs",
    "detect_missing_thumbnails",
    "import_scan_run",
    "empty_photo_trash",
    "refresh_custom_metrics",
    "worker_heartbeat",
    "cleanup_idempotency_keys",
    "send_meeting_email",
    "poll_meetings_rsvp",
    "send_rsvp_digest",
    "send_rsvp_final_digest",
    "process_email_outbox",
    "cleanup_email_outbox",
    "purge_kb_trash",
    "cleanup_kb_orphan_dirs",
    "poll_helpdesk_mailbox",
    "archive_closed_tickets_task",
    "create_next_helpdesk_archive_partition",
    "cleanup_helpdesk_attachments_task",
    "cleanup_expired_drafts_task",
    "send_helpdesk_digest",
    "run_erp_sync",
    "erp_sync_watchdog",
    "run_erp_absences_sync",
    "erp_absences_watchdog",
    "run_directum_sync",
    "directum_watchdog",
    "cleanup_module_runs",
    "recompute_daily_presence_status",
    "process_messenger_outbox",
    "cleanup_expired_resets",
    "process_deadline_reminders",
    "cleanup_messenger_outbox",
}

# Снапшот WorkerSettings.cron_jobs (имена корутин; FQN-строки резолвятся
# arq при построении списка).
EXPECTED_CRONS = {
    "flush_audit_queue",
    "create_next_audit_partition",
    "drop_old_audit_partitions",
    "publish_scheduled_news",
    "close_expired_polls",
    "archive_expired_news",
    "sync_users_from_keycloak",
    "cleanup_deleted_photos",
    "cleanup_expired_resets",
    "process_deadline_reminders",
    "cleanup_zip_jobs",
    "refresh_photo_storage",
    "detect_missing_thumbnails",
    "refresh_custom_metrics",
    "cleanup_idempotency_keys",
    "worker_heartbeat",
    "probe_integrations",
    "run_synthetic_probe",
    "process_email_outbox",
    "cleanup_email_outbox",
    "process_messenger_outbox",
    "cleanup_messenger_outbox",
    "cleanup_notifications",
    "purge_kb_trash",
    "cleanup_kb_orphan_dirs",
    "poll_helpdesk_mailbox",
    "poll_meetings_rsvp",
    "send_rsvp_digest",
    "send_rsvp_final_digest",
    "archive_closed_tickets_task",
    "create_next_helpdesk_archive_partition",
    "cleanup_helpdesk_attachments_task",
    "cleanup_expired_drafts_task",
    "send_helpdesk_digest",
    "run_erp_sync",
    "erp_sync_watchdog",
    "run_erp_absences_sync",
    "erp_absences_watchdog",
    "run_directum_sync",
    "directum_watchdog",
    "cleanup_module_runs",
    "recompute_daily_presence_status",
}

# Критичные dispatch-задачи: их потеря = молчаливая остановка целого
# контура (email/messenger/helpdesk/audit). Дублированы отдельным тестом —
# при падении снапшота сообщение называет виновника по имени.
CRITICAL_DISPATCH = {
    "process_email_outbox": "email-outbox: письма перестанут уходить",
    "process_messenger_outbox": "MAX/Matrix-уведомления перестанут уходить",
    "poll_helpdesk_mailbox": "helpdesk: заявки из email перестанут создаваться",
    "flush_audit_queue": "audit: очередь событий переполнится",
    "recompute_daily_presence_status": "статусы сотрудников перестанут пересчитываться",
}

# Review-3 (P2): ПОЛНЫЙ литеральный снапшот расписаний всех cron —
# (second, minute, hour, day, run_at_startup). Значения фиксированы один раз
# и НЕ импортируются из тестируемого модуля (урок TTL-таутологии): любое
# изменение реестра/расписания — осознанная правка этого снапшота. Меняется
# set на list-семантику: дубликаты регистрации ловятся отдельным тестом.
EXPECTED_CRON_SCHEDULES: dict[str, tuple] = {
    "archive_closed_tickets_task": (0, 20, 3, None, False),
    "archive_expired_news": (30, 0, None, None, False),
    "cleanup_deleted_photos": (0, 0, 4, None, False),
    "cleanup_email_outbox": (0, 15, 4, None, False),
    "cleanup_expired_drafts_task": (0, 0, 5, None, False),
    "cleanup_helpdesk_attachments_task": (0, 0, 4, None, False),
    "cleanup_idempotency_keys": (0, 30, 3, None, False),
    "cleanup_kb_orphan_dirs": (0, 45, 4, None, False),
    "cleanup_messenger_outbox": (0, 20, 4, None, False),
    "cleanup_module_runs": (0, 40, 4, None, False),
    "cleanup_notifications": (0, 25, 4, None, False),
    "cleanup_zip_jobs": (0, 0, 5, None, False),
    "close_expired_polls": (15, None, None, None, False),
    "create_next_audit_partition": (0, 0, 2, 1, True),
    "create_next_helpdesk_archive_partition": (0, 0, 2, 1, True),
    "detect_missing_thumbnails": (0, list(range(0, 60, 5)), None, None, False),
    "directum_watchdog": (0, 10, 9, None, False),
    "drop_old_audit_partitions": (0, 0, 3, 1, False),
    "erp_absences_watchdog": (0, 5, 9, None, False),
    "erp_sync_watchdog": (0, 0, 9, None, False),
    "flush_audit_queue": (list(range(0, 60, 5)), None, None, None, True),
    "poll_helpdesk_mailbox": ([0, 30], None, None, None, False),
    "poll_meetings_rsvp": ([0, 30], None, None, None, False),
    "probe_integrations": (0, list(range(0, 60)), None, None, False),
    "process_email_outbox": ([0, 10, 20, 30, 40, 50], None, None, None, True),
    "process_messenger_outbox": ([0, 15, 30, 45], None, None, None, True),
    "process_deadline_reminders": (0, 15, 7, None, False),
    "cleanup_expired_resets": (0, 45, 7, None, False),
    "publish_scheduled_news": (0, None, None, None, False),
    "purge_kb_trash": (0, 30, 4, None, False),
    "recompute_daily_presence_status": (0, 5, 0, None, False),
    "refresh_custom_metrics": ([0, 30], None, None, None, True),
    "refresh_photo_storage": (0, 35, 4, None, True),
    "run_directum_sync": (0, 17, None, None, False),
    "run_erp_absences_sync": (0, [5, 20, 35, 50], None, None, False),
    "run_erp_sync": (0, [0, 15, 30, 45], None, None, False),
    "run_synthetic_probe": (15, list(range(0, 60, 5)), None, None, False),
    "send_helpdesk_digest": (0, 0, None, None, False),
    "send_rsvp_digest": (10, [0, 30], None, None, False),
    "send_rsvp_final_digest": (45, None, None, None, False),
    "sync_users_from_keycloak": (0, 0, None, None, False),
    "worker_heartbeat": ([0, 30], None, None, None, True),
}


def _cron_records_by_name() -> dict[str, list]:
    """Все cron-записи по имени (list — дубликаты видны)."""
    from app.worker.main import WorkerSettings

    records: dict[str, list] = {}
    for job in WorkerSettings.cron_jobs:
        coroutine = getattr(job, "coroutine", None)
        name = getattr(coroutine, "__name__", None) or str(coroutine)
        records.setdefault(name, []).append(job)
    return records


def test_full_cron_schedule_snapshot() -> None:
    """Расписания всех cron литеральны: секунды/минуты/часы/дни/run_at_startup."""
    records = _cron_records_by_name()
    assert set(records) == set(EXPECTED_CRON_SCHEDULES), (
        f"состав cron-реестра изменился: +{sorted(set(records) - set(EXPECTED_CRON_SCHEDULES))} "
        f"-{sorted(set(EXPECTED_CRON_SCHEDULES) - set(records))} — обнови снапшот осознанно"
    )
    for name, expected in EXPECTED_CRON_SCHEDULES.items():
        job = records[name][0]
        actual = (
            sorted(job.second) if isinstance(job.second, (set, frozenset)) else job.second,
            sorted(job.minute) if isinstance(job.minute, (set, frozenset)) else job.minute,
            sorted(job.hour) if isinstance(job.hour, (set, frozenset)) else job.hour,
            sorted(job.day) if isinstance(job.day, (set, frozenset)) else job.day,
            job.run_at_startup,
        )
        exp = tuple(sorted(v) if isinstance(v, list) else v for v in expected)
        assert actual == exp, f"cron {name}: {actual} вместо {exp}"


def test_no_duplicate_registrations() -> None:
    """Дубликат регистрации (cron или function) = двойной dispatch; set-сет
    этого не видел. Проверяем СПИСКИ, не множества."""
    from app.worker.main import WorkerSettings

    cron_names = [
        getattr(j.coroutine, "__name__", str(j.coroutine)) for j in WorkerSettings.cron_jobs
    ]
    dupes = {n for n in cron_names if cron_names.count(n) > 1}
    assert not dupes, f"cron-задачи зарегистрированы дважды: {sorted(dupes)}"

    func_names = [
        (getattr(e, "name", None) or getattr(e, "__name__", None)) for e in WorkerSettings.functions
    ]
    dupes_f = {n for n in func_names if n and func_names.count(n) > 1}
    assert not dupes_f, f"functions зарегистрированы дважды: {sorted(dupes_f)}"


def test_arq_functions_registry_snapshot() -> None:
    registered = _registered_function_names()
    missing = EXPECTED_FUNCTIONS - registered
    extra = registered - EXPECTED_FUNCTIONS
    assert not missing, f"Из реестра воркера пропали задачи: {sorted(missing)}"
    assert not extra, (
        f"В реестре новые задачи {sorted(extra)} — если это осознанное добавление, "
        "дополните EXPECTED_FUNCTIONS (контрактный тест, аудит 2026-08-23)"
    )


def test_arq_cron_registry_snapshot() -> None:
    registered = _registered_cron_names()
    missing = EXPECTED_CRONS - registered
    extra = registered - EXPECTED_CRONS
    assert not missing, f"Из cron-реестра воркера пропали задачи: {sorted(missing)}"
    assert not extra, (
        f"В cron-реестре новые задачи {sorted(extra)} — если это осознанное "
        "добавление, дополните EXPECTED_CRONS (контрактный тест, аудит 2026-08-23)"
    )


def test_critical_dispatch_tasks_registered() -> None:
    registered = _registered_function_names() | _registered_cron_names()
    for task, consequence in CRITICAL_DISPATCH.items():
        assert task in registered, f"{task} не зарегистрирован: {consequence}"
