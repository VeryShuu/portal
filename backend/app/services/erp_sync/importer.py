"""Основная транзакция импорта ERP-выгрузки.

Оркестрирует :mod:`parser` → :mod:`matcher` → UPDATE ``users`` + diff → отчёт
в ``erp_sync_runs.report`` → уведомления (email_outbox + in-app).

Контракт «источник истины — ERP» (решение заказчика 2026-07-31): каждый
импорт **перетирает** ``birth_date``/``gender`` независимо от предыдущих
правок админа. Компенсация — в отчёт попадает diff old→new, чтобы админ видел
перетирание и мог реагировать через ERP.

Источник файла абстрагирован в :class:`Attachment` — один и тот же
``run_import`` используется и для mailbox-поллинга, и для ручного upload
(`POST /erp-sync/import-file`). Различаются только наполнением объекта.

Транзакционность (outbox-паттерн): бизнес-запись + ``erp_sync_runs`` +
``email_outbox`` + ``notifications`` — всё в одной сессии, один ``commit``;
SSE-publish колбэков — post-commit (best-effort, не откатывает импорт).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.erp_sync import ErpSyncRun
from app.models.user import User
from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email
from app.services.erp_sync.matcher import (
    Ambiguous,
    Unmatched,
    candidate_summary,
    match_row,
)
from app.services.erp_sync.parser import parse_attachment
from app.services.erp_sync.recipients import get_admin_user_ids, get_report_emails
from app.services.erp_sync.report import build_report_bodies, build_subject
from app.services.notifications import create_notification

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

# Лимит размеров списков в JSONB-отчёте, чтобы один кривой файл не раздул
# erp_sync_runs.report до мегабайт (много unmatched/ambiguous). Полные данные
# админ видит в письме; здесь — репрезентативная выборка + счётчики.
_MAX_REPORT_ITEMS = 200


@dataclass(frozen=True)
class Attachment:
    """Вложение, абстрагированное от источника (mailbox или upload).

    ``hash`` считается вызывающим кодом (sha256 содержимого) — используется
    для дедупа повторной загрузки того же файла.
    """

    filename: str
    data: bytes
    hash: str


async def run_import(
    db: AsyncSession,
    redis: Redis,
    *,
    attachment: Attachment,
    message_id: str | None,
    triggered_by: str,
) -> ErpSyncRun:
    """Выполнить один проход импорта.

    Args:
        db: async-сессия (одна транзакция для всего импорта + уведомлений).
        redis: для in-app SSE-publish.
        attachment: :class:`Attachment` (mailbox или upload).
        message_id: Message-ID письма (для дедупа в ``erp_sync_runs``);
            ``None`` для ручного upload.
        triggered_by: ``'cron'`` или ``'manual'``.

    Returns:
        Сохранённая запись :class:`ErpSyncRun` (status, счётчики, report).
    """
    started_at = datetime.now(UTC)

    # 1. Дедуп по message_id (только для mailbox-запуска; upload всегда новый).
    if message_id is not None:
        existing = (
            await db.execute(select(ErpSyncRun).where(ErpSyncRun.message_id == message_id))
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("erp_sync.import.skipped_duplicate", message_id=message_id)
            return existing

    # 2. Парсинг.
    parsed = parse_attachment(filename=attachment.filename, data=attachment.data)

    # 3. Per-row матчинг + UPDATE + сбор diff.
    changed: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    rows_matched = 0
    rows_updated = 0

    for row in parsed.rows:
        result = await match_row(db, row.fio)
        if isinstance(result, Unmatched):
            unmatched.append(
                {
                    "fio": row.fio,
                    "birth_date": row.birth_date.isoformat(),
                    "gender": row.gender,
                }
            )
            continue
        if isinstance(result, Ambiguous):
            rows_matched += 1  # сопоставлен, но неоднозначно
            ambiguous.append(
                {
                    "fio": row.fio,
                    "candidates": [candidate_summary(u) for u in result.candidates],
                }
            )
            continue
        # Matched — единственный кандидат.
        rows_matched += 1
        diff = await _update_user(db, result.user, row)
        if diff:  # есть реальные изменения
            rows_updated += 1
            changed.append({"fio": row.fio, "user_id": str(result.user.id), "fields": diff})

    # 4. Финальный статус run.
    has_problems = bool(unmatched or ambiguous or parsed.conflicts or parsed.errors)
    status = "partial" if has_problems else "success"
    # Если файл целиком не распарсился (нет ни одной валидной строки, и есть
    # ошибки) — это failed, даже если status-логика выше дала бы partial.
    if not parsed.rows and parsed.errors:
        status = "failed"

    # 5. Сборка JSONB-отчёта (с лимитами для размера).
    report: dict[str, Any] = {
        "changed": changed[:_MAX_REPORT_ITEMS],
        "unmatched": unmatched[:_MAX_REPORT_ITEMS],
        "ambiguous": ambiguous[:_MAX_REPORT_ITEMS],
        "conflicts": parsed.conflicts[:_MAX_REPORT_ITEMS],
        "errors": [e.__dict__ for e in parsed.errors[:_MAX_REPORT_ITEMS]],
        # Триггер для админа: списки урезаны?
        "truncated": {
            "changed": max(0, len(changed) - _MAX_REPORT_ITEMS),
            "unmatched": max(0, len(unmatched) - _MAX_REPORT_ITEMS),
            "ambiguous": max(0, len(ambiguous) - _MAX_REPORT_ITEMS),
            "conflicts": max(0, len(parsed.conflicts) - _MAX_REPORT_ITEMS),
            "errors": max(0, len(parsed.errors) - _MAX_REPORT_ITEMS),
        },
    }

    # 6. Запись лога импорта.
    run = ErpSyncRun(
        message_id=message_id,
        attachment_hash=attachment.hash,
        attachment_name=attachment.filename,
        triggered_by=triggered_by,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        status=status,
        rows_total=parsed.total_raw,
        rows_matched=rows_matched,
        rows_updated=rows_updated,
        rows_unmatched=len(unmatched),
        rows_ambiguous=len(ambiguous),
        conflicts=len(parsed.conflicts),
        errors=len(parsed.errors),
        report=report,
    )
    db.add(run)
    await db.flush()  # получить run.id до commit

    # 7. Уведомления (email + in-app) — в той же транзакции.
    await _enqueue_notifications(db, redis, run)

    await db.commit()

    # 8. Post-commit: опубликовать in-app уведомления в SSE-стримы.
    # Колбэки аккумулированы в _enqueue_notifications через run.id → нет, см. ниже:
    # create_notification возвращает publish-колбэк, но мы его дёрнули внутри.
    # (См. исправление: колбэки нужно вызывать после commit — вынесено в _publish_pending.)
    await _publish_pending(redis, run)

    logger.info(
        "erp_sync.import.done",
        run_id=run.id,
        status=status,
        rows_total=parsed.total_raw,
        rows_updated=rows_updated,
        unmatched=len(unmatched),
        ambiguous=len(ambiguous),
        conflicts=len(parsed.conflicts),
        errors=len(parsed.errors),
    )

    await db.refresh(run)
    return run


async def _update_user(
    db: AsyncSession,
    user: User,
    row: Any,  # row: ParsedRow, но Any чтобы не тащить тип
) -> dict[str, dict[str, Any]]:
    """Обновить birth_date/gender пользователя и вернуть diff old→new.

    Источник истины — ERP: перетираем всегда. Diff пустой, если значения не
    изменились (в отчёт «Обновлено» попадают только реальные изменения).

    Значения в diff сериализованы в JSON-совместимый вид (date → ISO-строка):
    ``report`` пишется в JSONB, а ``json.dumps`` (через SQLAlchemy) не умеет
    сериализовать ``date`` напрямую — был бы ``TypeError``.
    """
    diff: dict[str, dict[str, Any]] = {}
    if user.birth_date != row.birth_date:
        diff["birth_date"] = {
            "old": _json_value(user.birth_date),
            "new": _json_value(row.birth_date),
        }
    if user.gender != row.gender:
        diff["gender"] = {"old": user.gender, "new": row.gender}
    if not diff:
        return {}
    from app.api.users.users_repo import update_user_fields

    await update_user_fields(db, user.id, {"birth_date": row.birth_date, "gender": row.gender})
    return diff


def _json_value(value: Any) -> Any:
    """Привести значение к JSON-совместимому виду для записи в JSONB ``report``.

    ``date`` → ISO-строка (``json.dumps`` не умеет ``date`` напрямую).
    ``None``/``str`` проходят как есть.
    """
    if isinstance(value, date):
        return value.isoformat()
    return value


# Колбэки SSE-publish, аккумулированные до commit (атрибут на run — временный).
# SQLAlchemy не даст присвоить произвольный attr на mapped instance чисто,
# поэтому держим отдельный кэш keyed-by id(run).
_PENDING_PUBLISH: dict[int, list[Any]] = {}


async def _enqueue_notifications(db: AsyncSession, redis: Redis, run: ErpSyncRun) -> None:
    """Email-отчёт (email_outbox) + in-app (колокольчик) — без commit.

    Email: по списку адресов из get_report_emails (или явного override).
    In-app: всем админам с notify_inapp, type=erp_sync_report, link на историю.
    Колбэки SSE-публикации аккумулируются и дёргаются post-commit.
    """
    # Email — нужен settings для notify_emails override. Загружаем singleton.
    from app.models.erp_sync import ErpSyncSettings

    settings = (
        await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    ).scalar_one_or_none()
    emails = await get_report_emails(db, settings) if settings is not None else []
    if emails:
        html_body, plain_body = build_report_bodies(run)
        subject = build_subject(run)
        for email in emails:
            await enqueue_outbox_email(
                db,
                kind=KIND_GENERIC,
                to_email=email,
                subject=subject,
                body_html=html_body,
                body_text=plain_body,
                payload={"erp_sync_run_id": run.id},
                related_resource_type="erp_sync_run",
                related_resource_id=None,  # run.id — bigint, не UUID; несём в payload
            )

    # In-app — всем админам. Колбэки аккумулируем.
    publish_callbacks: list[Any] = []
    admin_ids = await get_admin_user_ids(db)
    title = build_subject(run)
    attention = (
        (run.rows_unmatched or 0)
        + (run.rows_ambiguous or 0)
        + (run.conflicts or 0)
        + (run.errors or 0)
    )
    body = f"Обновлено: {run.rows_updated or 0}. Требуют внимания: {attention}."
    for uid in admin_ids:
        publish = await create_notification(
            db,
            redis,
            user_id=uid,
            type="erp_sync_report",
            title=title,
            body=body,
            link="/admin?tab=erp_sync",
        )
        publish_callbacks.append(publish)
    _PENDING_PUBLISH[id(run)] = publish_callbacks


async def _publish_pending(redis: Redis, run: ErpSyncRun) -> None:
    """Дёрнуть SSE-publish колбэки после commit (best-effort).

    SSE-публикация в Redis-стрим — не часть бизнес-транзакции: если упадёт,
    импорт уже закоммичен, уведомление просто не всплывёт мгновенно
    (пользователь увидит при следующем заходе — notification-строк есть).
    """
    callbacks = _PENDING_PUBLISH.pop(id(run), [])
    for publish in callbacks:
        try:
            await publish()
        except Exception:
            logger.warning("erp_sync.notification.publish_failed", exc_info=True)


def attachment_hash(data: bytes) -> str:
    """SHA256 хэш содержимого вложения (для дедупа и лога)."""
    return hashlib.sha256(data).hexdigest()
