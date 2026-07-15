"""Unit-тесты фильтра ARQ-логов высокочастотных cron-задач."""

from __future__ import annotations

import logging

from app.worker._arq_log_filter import (
    QUIET_CRON_REFS,
    QuietCronFilter,
)


def _record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="arq.worker",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


# ---------------------------------------------------------------------------
# Старт/финиш высокочастотных cron-задач → гасим
# ---------------------------------------------------------------------------


def test_quiet_cron_start_filtered() -> None:
    f = QuietCronFilter()
    # ARQ формат старта: '%6.2fs → ref(args)extra'
    for ref in QUIET_CRON_REFS:
        rec = _record(f"   0.00s → {ref}()")
        assert f.filter(rec) is False, f"должен гасить старт {ref}"


def test_quiet_cron_end_filtered() -> None:
    f = QuietCronFilter()
    # ARQ формат успешного завершения: '%6.2fs ← ref ● result'
    for ref in QUIET_CRON_REFS:
        rec = _record(f"   0.01s ← {ref} ● 0")
        assert f.filter(rec) is False, f"должен гасить финиш {ref}"


# ---------------------------------------------------------------------------
# Редкие cron и ручные задачи → оставляем
# ---------------------------------------------------------------------------


def test_rare_cron_kept() -> None:
    """Разминутный/часовой cron логируется редко — оставляем след."""
    f = QuietCronFilter()
    rare = [
        "cron:app.worker.tasks.news.publish_scheduled_news",
        "cron:app.worker.tasks.news.sync_users_from_keycloak",
        "cron:app.worker.tasks.photos.cleanup_deleted_photos",
        "cron:app.worker.tasks.audit.create_next_audit_partition",
    ]
    for ref in rare:
        assert f.filter(_record(f"   1.00s ← {ref} ● 1")) is True
        assert f.filter(_record(f"   0.00s → {ref}()")) is True


def test_manual_job_kept() -> None:
    """Ручные (не-cron) задачи — всегда видимы (без префикса 'cron:')."""
    f = QuietCronFilter()
    assert f.filter(_record("   2.50s → process_photo_upload('uuid-1')")) is True
    assert f.filter(_record("   2.50s ← generate_folder_zip('uuid-1') ● 'ok'")) is True


def test_quiet_ref_as_substring_of_manual_not_filtered() -> None:
    """Защита от ложного срабатывания: ручная задача, чьё имя содержит
    подстроку тихого ref, не должна гаситься."""
    f = QuietCronFilter()
    # Имя функции содержит 'flush_audit_queue', но это не cron-задача.
    rec = _record("   1.00s → manual_flush_audit_queue_debug()")
    assert f.filter(rec) is True


# ---------------------------------------------------------------------------
# Ошибки, ретраи, прерывания → всегда оставляем (уровень или маркер)
# ---------------------------------------------------------------------------


def test_quiet_cron_failure_kept() -> None:
    """Ошибка тихой cron-задачи (logger.exception, '!') критична — оставляем."""
    f = QuietCronFilter()
    for ref in QUIET_CRON_REFS:
        rec = _record(f"   5.00s ! {ref} failed, RuntimeError: boom")
        assert f.filter(rec) is True, f"ошибка {ref} должна быть видна"


def test_quiet_cron_retry_kept() -> None:
    """Ретрай тихой cron-задачи ('↻') оставляем."""
    f = QuietCronFilter()
    rec = _record("   0.00s ↻ cron:app.worker.tasks.audit.flush_audit_queue retrying job in 1.00s")
    assert f.filter(rec) is True


def test_warning_level_always_kept() -> None:
    """Любая запись WARNING+ проходит фильтр независимо от содержания."""
    f = QuietCronFilter()
    for ref in QUIET_CRON_REFS:
        rec = _record(f"   0.00s ← {ref} ● 0", level=logging.WARNING)
        assert f.filter(rec) is True
        rec = _record(f"  10.0s ← {ref} ● 0", level=logging.ERROR)
        assert f.filter(rec) is True


# ---------------------------------------------------------------------------
# Не-задачные сообщения ARQ → оставляем
# ---------------------------------------------------------------------------


def test_arq_banner_kept() -> None:
    """Стартовые/системные баннеры ARQ (без маркеров →/←) — оставляем."""
    f = QuietCronFilter()
    assert f.filter(_record("Starting worker for 30 functions: ...")) is True
    assert f.filter(_record("redis_version=7.2.4")) is True
    assert f.filter(_record("recording health: Jul-11 j_complete=1 j_failed=0")) is True


def test_empty_message_kept() -> None:
    f = QuietCronFilter()
    assert f.filter(_record("")) is True
