"""Основная транзакция импорта отчёта отсутствий ERP.

Клон :mod:`importer` (поток дней рождения), но с **full-replace** вместо
per-field upsert. Отчёт «Кадровая история сотрудников за период» самодостаточен
(содержит весь период — обычно год), поэтому каждый импорт:

1. Парсит файл (через :mod:`absences_parser`).
2. Сопоставляет ФИО с пользователями (через :mod:`matcher` — общий с днями рождения).
3. При наличии валидных matched-строк: ``DELETE FROM erp_absences WHERE
   source='erp_sync'`` → bulk ``INSERT``. Старые записи сотрудников, исчезнувших
   из ERP, стираются автоматически.
4. При отсутствии валидных строк (``status='failed'``) — БД **не трогаем**:
   иначе одно битое письмо сотрёт всю историю отсутствий.
5. Лог в ``erp_absences_runs`` + уведомления (email_outbox + in-app).

Транзакционность (outbox-паттерн): бизнес-запись + лог + email_outbox +
notifications — в одной сессии, один ``commit``; SSE-publish — post-commit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.erp_sync import ErpAbsence, ErpAbsencesRun
from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email
from app.services.erp_sync.absences_parser import parse_absences_attachment
from app.services.erp_sync.absences_report import (
    build_absences_report_bodies,
    build_absences_subject,
)
from app.services.erp_sync.matcher import (
    Ambiguous,
    Unmatched,
    candidate_summary,
    match_row,
)
from app.services.erp_sync.recipients import get_admin_user_ids, get_report_emails
from app.services.notifications import create_notification

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

# Лимит размеров списков в JSONB-отчёте (клон importer._MAX_REPORT_ITEMS).
_MAX_REPORT_ITEMS = 200


@dataclass(frozen=True)
class AbsenceAttachment:
    """Вложение отчёта отсутствий, абстрагированное от источника (mailbox/upload)."""

    filename: str
    data: bytes
    hash: str


async def run_absences_import(
    db: AsyncSession,
    redis: Redis,
    *,
    attachment: AbsenceAttachment,
    message_id: str | None,
    triggered_by: str,
) -> ErpAbsencesRun:
    """Выполнить один проход импорта отсутствий (full-replace).

    Args:
        db: async-сессия (одна транзакция для всего импорта + уведомлений).
        redis: для in-app SSE-publish.
        attachment: :class:`AbsenceAttachment` (mailbox или upload).
        message_id: Message-ID письма (для дедупа в ``erp_absences_runs``);
            ``None`` для ручного upload.
        triggered_by: ``'cron'`` или ``'manual'``.

    Returns:
        Сохранённая запись :class:`ErpAbsencesRun` (status, счётчики, report).
    """
    started_at = datetime.now(UTC)

    # 1. Дедуп по message_id (только для mailbox-запуска; upload всегда новый).
    if message_id is not None:
        existing = (
            await db.execute(select(ErpAbsencesRun).where(ErpAbsencesRun.message_id == message_id))
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("erp_sync.absences_import.skipped_duplicate", message_id=message_id)
            return existing

    # 2. Парсинг.
    parsed = parse_absences_attachment(filename=attachment.filename, data=attachment.data)

    # 3. Per-row матчинг. INSERT не делаем в цикле — собираем объекты для bulk-insert.
    inserted: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    rows_matched = 0

    # Группируем matched-строки по user_id для bulk-insert (один пользователь
    # может иметь несколько периодов отсутствий — каждый отдельной строкой).
    absence_rows: list[ErpAbsence] = []

    for row in parsed.rows:
        result = await match_row(db, row.fio)
        if isinstance(result, Unmatched):
            unmatched.append(
                {
                    "fio": row.fio,
                    "kind": row.kind,
                    "start_date": row.start_date.isoformat(),
                    "end_date": row.end_date.isoformat(),
                }
            )
            continue
        if isinstance(result, Ambiguous):
            rows_matched += 1
            ambiguous.append(
                {
                    "fio": row.fio,
                    "candidates": [candidate_summary(u) for u in result.candidates],
                }
            )
            continue
        # Matched — единственный кандидат.
        rows_matched += 1
        absence_rows.append(
            ErpAbsence(
                user_id=result.user.id,
                kind=row.kind,
                position=row.position,
                department=row.department,
                start_date=row.start_date,
                end_date=row.end_date,
                source="erp_sync",
            )
        )
        inserted.append(
            {
                "fio": row.fio,
                "user_id": str(result.user.id),
                "kind": row.kind,
                "position": row.position,
                "department": row.department,
                "start_date": row.start_date.isoformat(),
                "end_date": row.end_date.isoformat(),
            }
        )

    # 4. Full-replace: только при наличии валидных matched-строк. При 0 строк
    # (битый файл / ничего не распознано) — БД не трогаем, status='failed'.
    rows_inserted = 0
    if absence_rows:
        await db.execute(delete(ErpAbsence).where(ErpAbsence.source == "erp_sync"))
        db.add_all(absence_rows)
        rows_inserted = len(absence_rows)
        await db.flush()  # получить id для логов/диагностики

    # 5. Финальный статус run.
    has_problems = bool(unmatched or ambiguous or parsed.errors)
    if not absence_rows and parsed.errors:
        # Файл целиком не распарсился → failed (БД не тронули).
        status = "failed"
    elif not absence_rows and not has_problems:
        # Файл пустой (0 строк, 0 ошибок) — пропускаем молча, не failed.
        status = "skipped"
    else:
        status = "partial" if has_problems else "success"

    # 6. Сборка JSONB-отчёта (с лимитами для размера).
    report: dict[str, Any] = {
        "inserted": inserted[:_MAX_REPORT_ITEMS],
        "unmatched": unmatched[:_MAX_REPORT_ITEMS],
        "ambiguous": ambiguous[:_MAX_REPORT_ITEMS],
        "errors": [e.__dict__ for e in parsed.errors[:_MAX_REPORT_ITEMS]],
        "truncated": {
            "inserted": max(0, len(inserted) - _MAX_REPORT_ITEMS),
            "unmatched": max(0, len(unmatched) - _MAX_REPORT_ITEMS),
            "ambiguous": max(0, len(ambiguous) - _MAX_REPORT_ITEMS),
            "errors": max(0, len(parsed.errors) - _MAX_REPORT_ITEMS),
        },
    }

    # 7. Запись лога импорта.
    run = ErpAbsencesRun(
        message_id=message_id,
        attachment_hash=attachment.hash,
        attachment_name=attachment.filename,
        triggered_by=triggered_by,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        status=status,
        rows_total=parsed.total_raw,
        rows_matched=rows_matched,
        rows_inserted=rows_inserted,
        rows_unmatched=len(unmatched),
        rows_ambiguous=len(ambiguous),
        errors=len(parsed.errors),
        report=report,
    )
    db.add(run)
    await db.flush()  # получить run.id до commit

    # 8. Уведомления (email + in-app) — в той же транзакции.
    await _enqueue_notifications(db, redis, run)

    await db.commit()

    # 9. Post-commit: опубликовать in-app уведомления в SSE-стримы.
    await _publish_pending(redis, run)

    logger.info(
        "erp_sync.absences_import.done",
        run_id=run.id,
        status=status,
        rows_total=parsed.total_raw,
        rows_inserted=rows_inserted,
        unmatched=len(unmatched),
        ambiguous=len(ambiguous),
        errors=len(parsed.errors),
    )

    await db.refresh(run)
    return run


# Колбэки SSE-publish, аккумулированные до commit. Кеш keyed-by id(run) —
# SQLAlchemy не даст присвоить произвольный attr на mapped instance чисто.
_PENDING_PUBLISH: dict[int, list[Any]] = {}


async def _enqueue_notifications(db: AsyncSession, redis: Redis, run: ErpAbsencesRun) -> None:
    """Email-отчёт + in-app (колокольчик) — без commit. Клон importer._enqueue_notifications."""
    from app.models.erp_sync import ErpSyncSettings

    settings = (
        await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()
    emails = await get_report_emails(db, settings) if settings is not None else []
    if emails:
        html_body, plain_body = build_absences_report_bodies(run)
        subject = build_absences_subject(run)
        for email in emails:
            await enqueue_outbox_email(
                db,
                kind=KIND_GENERIC,
                to_email=email,
                subject=subject,
                body_html=html_body,
                body_text=plain_body,
                payload={"erp_absences_run_id": run.id},
                related_resource_type="erp_absences_run",
                related_resource_id=None,
            )

    publish_callbacks: list[Any] = []
    admin_ids = await get_admin_user_ids(db)
    title = build_absences_subject(run)
    attention = (run.rows_unmatched or 0) + (run.rows_ambiguous or 0) + (run.errors or 0)
    body = f"Добавлено: {run.rows_inserted or 0}. Требуют внимания: {attention}."
    for uid in admin_ids:
        publish = await create_notification(
            db,
            redis,
            user_id=uid,
            type="erp_absences_report",
            title=title,
            body=body,
            link="/admin?tab=erp_sync",
        )
        publish_callbacks.append(publish)
    _PENDING_PUBLISH[id(run)] = publish_callbacks


async def _publish_pending(redis: Redis, run: ErpAbsencesRun) -> None:
    """Дёрнуть SSE-publish колбэки после commit (best-effort)."""
    callbacks = _PENDING_PUBLISH.pop(id(run), [])
    for publish in callbacks:
        try:
            await publish()
        except Exception:
            logger.warning("erp_sync.absences_notification.publish_failed", exc_info=True)


def absence_attachment_hash(data: bytes) -> str:
    """SHA256 хэш содержимого вложения (для дедупа и лога)."""
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "AbsenceAttachment",
    "absence_attachment_hash",
    "run_absences_import",
]
