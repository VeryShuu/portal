"""Оркестрация прогона Directum «Просроченные задачи».

Пайплайн (одна транзакция — outbox-инвариант):

1. OData-запрос всех просроченных задач в работе (:mod:`odata`).
2. Группировка по исполнителю (ФИО из ``Performer.Name``).
3. Матчинг ФИО → пользователь портала (:mod:`matcher`).
4. Найденным с включённым ``chat_notifications_enabled`` — дайджест в
   ``messenger_outbox`` (provider=matrix, ``chat_id`` = MXID по конвенции из
   email; DM-комнату резолвит воркер доставки).
5. Run-строка со счётчиками + JSONB-отчёт + email-сводка админам
   (:mod:`report`, :mod:`recipients`) — один ``db.commit()``.

Решения зафиксированы с пользователем: уведомляем **каждый прогон** (нет
dedup-таблицы); opt-in соблюдаем — выключенные попадают в
``report.skipped_opt_in`` (actionable для админа), но не портят статус.
Email-сводка шлётся только когда есть о чём рассказать (задачи есть или
прогон неуспешен) — пустой ежедневный «0 задач» был бы шумом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret
from app.models.directum import DirectumRun, DirectumSettings
from app.models.matrix_bot import MatrixBotSettings
from app.services.directum.digest import build_overdue_digest
from app.services.directum.matcher import (
    Ambiguous,
    Unmatched,
    candidate_summary,
    match_performer,
)
from app.services.directum.odata import (
    DirectumApiError,
    classify_error,
    fetch_overdue_assignments,
    now_directum,
)
from app.services.directum.recipients import get_report_emails
from app.services.directum.report import build_report_bodies, build_subject
from app.services.email_outbox import KIND_DIRECTUM, enqueue_outbox_email
from app.services.matrix_messenger import matrix_id_for_user
from app.services.messenger_outbox import PROVIDER_MATRIX, enqueue_messenger_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User
    from app.services.directum.odata import OverdueAssignment

logger = get_logger(__name__)

# Кап на каждый список в JSONB-отчёте (как _MAX_REPORT_ITEMS в erp_sync):
# однофамильцы/не найденные могут исчисляться сотнями — в письмо хватает 200.
MAX_REPORT_ITEMS = 200


async def load_directum_settings(db: AsyncSession) -> DirectumSettings | None:
    """Singleton настроек (id=1); None — теоретически невозможен (сеет миграция)."""
    return (
        await db.execute(select(DirectumSettings).where(DirectumSettings.id == 1))
    ).scalar_one_or_none()


def directum_configured(settings: DirectumSettings) -> bool:
    """Креды полны — можно ходить в OData (пароль задан, логин/base_url непустые)."""
    return bool(settings.base_url and settings.auth_username and settings.auth_password_enc)


async def _load_matrix_settings(db: AsyncSession) -> MatrixBotSettings | None:
    return (
        await db.execute(select(MatrixBotSettings).where(MatrixBotSettings.id == 1))
    ).scalar_one_or_none()


def _matrix_ready(row: MatrixBotSettings | None) -> bool:
    """Matrix-канал доставки настроен (без него дайджесты некому отправлять)."""
    return bool(
        row
        and row.enabled
        and row.access_token_enc
        and row.homeserver_url
        and row.server_name
        and row.bot_user_id
    )


@dataclass
class _Outcome:
    """Накопитель результата обработки исполнителей (до финализации run)."""

    notified: list[dict] = field(default_factory=list)
    skipped_opt_in: list[dict] = field(default_factory=list)
    unmatched: list[dict] = field(default_factory=list)
    ambiguous: list[dict] = field(default_factory=list)
    skipped_matrix: list[str] = field(default_factory=list)
    matrix_ready: bool = True
    performers_total: int = 0
    errors: int = 0


async def run_directum_sync(db: AsyncSession, *, triggered_by: str = "cron") -> DirectumRun:
    """Один прогон: fetch → матчинг → уведомления → отчёт. Коммитит сам.

    Оркестрация тонкая (CC-гейт ≤10): содержательные шаги — в под-функциях
    :func:`_record_failed_run` / :func:`_process_all_performers` /
    :func:`_finalize_run`.
    """
    settings = await load_directum_settings(db)
    if settings is None or not directum_configured(settings):
        # Не должно случиться (PUT валидирует, воркер гейтит) — но защитно.
        raise RuntimeError("directum settings are not configured")

    password = decrypt_secret(settings.auth_password_enc)  # type: ignore[arg-type]
    now_local = now_directum()
    started_at = datetime.now(UTC)

    # ── 1. Fetch. Сбой OData → failed-run + короткий алерт админам. ─────────
    try:
        tasks = await fetch_overdue_assignments(
            base_url=settings.base_url,
            username=settings.auth_username or "",
            password=password,
            now=now_local,
        )
    except DirectumApiError as exc:
        return await _record_failed_run(
            db, settings, triggered_by=triggered_by, started_at=started_at, exc=exc
        )

    # ── 2..5: run-строку создаём до enqueue (payload ссылается на run_id). ──
    run = DirectumRun(
        triggered_by=triggered_by,
        started_at=started_at,
        status="success",  # финализируем ниже (partial при проблемах доставки)
        tasks_total=len(tasks),
    )
    db.add(run)
    await db.flush()

    outcome = await _process_all_performers(db, run, tasks, now_local)
    _finalize_run(run, outcome)

    # Email-сводка: только если есть содержание (задачи/проблемы) — не шлём
    # ежедневное «0 задач».
    if run.tasks_total or run.status != "success":
        await _enqueue_run_emails(db, settings, run)

    await db.commit()
    logger.info(
        "directum.sync.done",
        run_id=run.id,
        status=run.status,
        tasks=run.tasks_total,
        notified=run.users_notified,
        skipped_opt_in=run.users_skipped_opt_in,
        unmatched=run.users_unmatched,
        ambiguous=run.users_ambiguous,
    )
    return run


async def _record_failed_run(
    db: AsyncSession,
    settings: DirectumSettings,
    *,
    triggered_by: str,
    started_at: datetime,
    exc: DirectumApiError,
) -> DirectumRun:
    """Сбой OData: failed-run с причиной + алерт админам (тот же commit)."""
    logger.warning(
        "directum.sync.fetch_failed",
        status=getattr(exc, "status_code", None),
        error=str(exc)[:300],
    )
    run = DirectumRun(
        triggered_by=triggered_by,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        status="failed",
        errors=1,
        report={
            "error": str(exc)[:500],
            "error_class": classify_error(exc),
        },
    )
    db.add(run)
    await db.flush()
    await _enqueue_run_emails(db, settings, run)
    await db.commit()
    return run


async def _process_all_performers(
    db: AsyncSession,
    run: DirectumRun,
    tasks: list[OverdueAssignment],
    now_local: datetime,
) -> _Outcome:
    """Матчинг + уведомления по каждому исполнителю; копит :class:`_Outcome`."""
    matrix_row = await _load_matrix_settings(db)
    outcome = _Outcome(matrix_ready=_matrix_ready(matrix_row))
    server_name = matrix_row.server_name if matrix_row else ""

    # Группировка задач по исполнителю (первое вхождение сохраняет порядок).
    grouped: dict[str, list[OverdueAssignment]] = {}
    for task in tasks:
        grouped.setdefault(task.performer_name or "", []).append(task)
    outcome.performers_total = len(grouped)

    for performer_name, items in grouped.items():
        try:
            await _process_one_performer(
                db, run, performer_name, items, outcome, server_name, now_local
            )
        except Exception:
            # Один исполнитель не должен ронять прогон целиком.
            outcome.errors += 1
            logger.exception(
                "directum.sync.performer_failed",
                performer=performer_name or "(исполнитель не указан)",
            )
    return outcome


async def _process_one_performer(
    db: AsyncSession,
    run: DirectumRun,
    performer_name: str,
    items: list[OverdueAssignment],
    outcome: _Outcome,
    server_name: str,
    now_local: datetime,
) -> None:
    """Триаж одного исполнителя: unmatched/ambiguous/opt-out/дайджест."""
    display = performer_name or "(исполнитель не указан)"
    entry = {"fio": display, "tasks": len(items)}

    if not performer_name:
        outcome.unmatched.append(entry)
        return
    match = await match_performer(db, performer_name)
    if isinstance(match, Ambiguous):
        outcome.ambiguous.append(
            {**entry, "candidates": [candidate_summary(u) for u in match.candidates]}
        )
    elif isinstance(match, Unmatched):
        outcome.unmatched.append(entry)
    else:
        await _deliver_to_user(db, run, match.user, display, items, outcome, server_name, now_local)


async def _deliver_to_user(
    db: AsyncSession,
    run: DirectumRun,
    user: User,
    display: str,
    items: list[OverdueAssignment],
    outcome: _Outcome,
    server_name: str,
    now_local: datetime,
) -> None:
    """Доставка найденному сотруднику: opt-in-гейт → дайджест в outbox."""
    entry = {"fio": display, "tasks": len(items)}
    if not bool((user.preferences or {}).get("chat_notifications_enabled")):
        outcome.skipped_opt_in.append(entry)
        return
    if not outcome.matrix_ready:
        outcome.skipped_matrix.append(display)
        return
    plain, formatted = build_overdue_digest(items, now=now_local)
    await enqueue_messenger_message(
        db,
        provider=PROVIDER_MATRIX,
        chat_id=matrix_id_for_user(user.email, server_name),
        text=plain,
        payload={"formatted_body": formatted, "directum_run_id": run.id},
        related_resource_type="directum_run",
    )
    outcome.notified.append(entry)


def _finalize_run(run: DirectumRun, outcome: _Outcome) -> None:
    """Счётчики/статус/JSONB-отчёт по накопленному :class:`_Outcome`."""
    run.performers_total = outcome.performers_total
    run.users_notified = len(outcome.notified)
    run.users_skipped_opt_in = len(outcome.skipped_opt_in)
    run.users_unmatched = len(outcome.unmatched)
    run.users_ambiguous = len(outcome.ambiguous)
    run.errors = outcome.errors
    run.finished_at = datetime.now(UTC)
    run.status = (
        "partial"
        if (outcome.errors > 0 or (not outcome.matrix_ready and outcome.skipped_matrix))
        else "success"
    )

    report: dict = {
        "notified": outcome.notified[:MAX_REPORT_ITEMS],
        "skipped_opt_in": outcome.skipped_opt_in[:MAX_REPORT_ITEMS],
        "unmatched": outcome.unmatched[:MAX_REPORT_ITEMS],
        "ambiguous": outcome.ambiguous[:MAX_REPORT_ITEMS],
        "matrix_disabled": bool(outcome.skipped_matrix) or None,
        "skipped_matrix_disabled": outcome.skipped_matrix[:MAX_REPORT_ITEMS] or None,
        "truncated": any(
            len(lst) > MAX_REPORT_ITEMS
            for lst in (
                outcome.notified,
                outcome.skipped_opt_in,
                outcome.unmatched,
                outcome.ambiguous,
            )
        ),
    }
    run.report = {k: v for k, v in report.items() if v is not None}


async def _enqueue_run_emails(
    db: AsyncSession, settings: DirectumSettings, run: DirectumRun
) -> None:
    """Сводка (или алерт о сбое) всем адресатам — в той же транзакции."""
    subject = build_subject(run)
    html_body, plain_body = build_report_bodies(run)
    for email in await get_report_emails(db, settings):
        await enqueue_outbox_email(
            db,
            kind=KIND_DIRECTUM,
            to_email=email,
            subject=subject,
            body_html=html_body,
            body_text=plain_body,
            payload={"directum_run_id": run.id},
            related_resource_type="directum_run",
        )
