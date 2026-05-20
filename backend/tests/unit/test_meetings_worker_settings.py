"""TST-03: ARQ WorkerSettings must NOT register cleanup_meetings_audit (BLK-01).

The `meetings_audit_log` table was dropped by migration 050. Any cron-job that
tries to delete from it would crash with `ProgrammingError`. This regression
test guards against accidental re-introduction.
"""

from __future__ import annotations


def test_worker_settings_has_no_cleanup_meetings_audit() -> None:
    from app.worker.main import WorkerSettings

    func_names = {getattr(fn, "__name__", str(fn)) for fn in WorkerSettings.functions}
    assert "cleanup_meetings_audit" not in func_names

    cron_targets = {getattr(c, "coroutine", None) for c in WorkerSettings.cron_jobs}
    cron_str_targets = {str(c) for c in WorkerSettings.cron_jobs}
    assert not any(
        "cleanup_meetings_audit" in s for s in cron_str_targets
    ), "cleanup_meetings_audit cron-job must be removed (table dropped in migration 050)"

    for target in cron_targets:
        name = getattr(target, "__name__", "") if target is not None else ""
        assert "cleanup_meetings_audit" not in name


def test_send_meeting_email_registered() -> None:
    from app.worker.main import WorkerSettings
    from app.worker.tasks.meetings.email import send_meeting_email

    assert send_meeting_email in WorkerSettings.functions
