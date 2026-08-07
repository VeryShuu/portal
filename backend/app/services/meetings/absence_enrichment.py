"""Enrich приглашённых на встречу статусом отсутствия (отпуск/отгул/болезнь/командировка).

Статус отсутствия **не хранится** в JSONB-слепке ``meeting_bookings.invited_users``:
он пересчитывается ежедневно cron'ом из ERP (см.
:mod:`app.services.erp_sync.absences_status`), и запечённый в слепок устарел бы
за сутки. Поэтому обогащение идёт «на лету» в трёх точках:

* :func:`enrich_absences_for_invited` — общая bulk-логика для бронирований и
  писем: для каждого участника-сотрудника (``source == 'keycloak'``) находит
  отсутствие, действующее на ``on_date`` (дату встречи), и возвращает
  :class:`~app.schemas.meetings.AbsenceInfo`. Один bulk-запрос на весь список.
* callers в ``app.api.meetings._mappers`` (для выдачи бронирования) и
  ``app.services.meetings.notifications`` (для email-приглашения) вызывают её с
  ``on_date = booking.start_time.date()``.
* live-поиск (``app.api.meetings.participants``) идёт через
  :func:`current_status_snapshot` — берёт уже посчитанный ``users.current_status``
  на «сегодня» (даты встречи в момент поиска ещё нет).

Приоритет категорий при пересечении нескольких одновременных отсутствий
повторяет :mod:`absences_status`: ``sick`` > ``vacation`` > ``business_trip``
(больной в командировке → показываем «болезнь»).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.erp_sync import ErpAbsence
from app.models.user import User
from app.schemas.meetings import AbsenceInfo
from app.services.erp_sync.absences_status import kind_to_category

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Приоритет категории при пересечении нескольких одновременных отсутствий.
# Меньше = выше (sick > vacation > business_trip), как в absences_status.py.
# ``working`` сюда не входит — AbsenceInfo.category не допускает ``working``
# (отсутствие = всё, что не ``working``).
_CATEGORY_PRIORITY: dict[str, int] = {"sick": 0, "vacation": 1, "business_trip": 2}


def _category_priority(category: str) -> int:
    return _CATEGORY_PRIORITY.get(category, 99)


def _extract_email(u: Any) -> str:
    """Email участника из dict (JSONB) или InvitedUser."""
    if isinstance(u, dict):
        return str(u.get("email") or "")
    return str(getattr(u, "email", "") or "")


def _is_keycloak(u: Any) -> bool:
    """Только сотрудники (``source == 'keycloak'``). Внешних пропускаем."""
    if isinstance(u, dict):
        return bool(u.get("source", "keycloak") == "keycloak")
    return bool(getattr(u, "source", "keycloak") == "keycloak")


async def enrich_absences_for_invited(
    db: AsyncSession,
    invited: list[Any],
    *,
    on_date: date,
) -> dict[str, AbsenceInfo]:
    """Вернуть absence-инфо для участников-сотрудников, ключ — ``lower(email)``.

    Один bulk-запрос: JOIN ``erp_absences`` с ``users`` по ``user_id``, фильтр по
    пересечению диапазона отсутствия с ``on_date`` и по нижним email'ам
    приглашённых. При множественных пересекающихся отсутствиях одного
    сотрудника выбирается приоритетная категория (sick > vacation > business_trip).

    Внешние участники (``source == 'external'``), пустые email и записи без
    отсутствия на ``on_date`` в результат не попадают.

    Args:
        db: активная сессия (caller управляет транзакцией).
        invited: список участников (``InvitedUser`` или dict из JSONB).
        on_date: дата, на которую ищем действующее отсутствие (обычно —
            дата встречи ``booking.start_time.date()``).

    Returns:
        Словарь ``{lower(email): AbsenceInfo}``. Для участников без отсутствия
        записи нет — caller заполняет ``InvitedUser.absence = None``.
    """
    emails = [_extract_email(u).lower() for u in invited if _is_keycloak(u) and _extract_email(u)]
    if not emails:
        return {}

    rows = (
        await db.execute(
            select(
                func.lower(User.email).label("email"),
                ErpAbsence.kind,
                ErpAbsence.start_date,
                ErpAbsence.end_date,
            )
            .join(User, User.id == ErpAbsence.user_id)
            .where(
                ErpAbsence.start_date <= on_date,
                ErpAbsence.end_date >= on_date,
                func.lower(User.email).in_(emails),
            )
        )
    ).all()

    # Схлопываем по email: оставляем приоритетную категорию (больной в
    # командировке → sick). kind→category маппится через единый источник истины
    # (kind_to_category), чтобы не дублировать CASE-логику в SQL.
    by_email: dict[str, AbsenceInfo] = {}
    for row in rows:
        category = kind_to_category(row.kind)
        if category == "working":  # неизвестный kind — пропускаем (защита)
            continue
        existing = by_email.get(row.email)
        if existing is None or _category_priority(category) < _category_priority(existing.category):
            by_email[row.email] = AbsenceInfo(
                category=category,  # type: ignore[arg-type]
                start_date=row.start_date,
                end_date=row.end_date,
            )
    return by_email


async def current_status_snapshot(
    db: AsyncSession,
    emails: list[str],
) -> dict[str, AbsenceInfo]:
    """Текущий статус отсутствия («на сегодня») для live-поиска участников.

    В отличие от :func:`enrich_absences_for_invited`, не лезет в ``erp_absences``
    по диапазону — берёт уже посчитанный cron'ом ``users.current_status`` /
    ``current_status_until`` (как справочник сотрудников). Дата встречи в момент
    поиска ещё неизвестна, поэтому используется «сегодня».

    ``start_date``/``end_date`` в :class:`AbsenceInfo` заполняются одинаковым
    значением ``current_status_until`` (для UI это «до {дата}»), т.к. точный
    ``start_date`` текущего отсутствия здесь не нужен — подпись в live-поиске
    показывает только категорию и дату окончания.

    Args:
        db: активная сессия.
        emails: список email'ов сотрудников (регистр нормализуется).

    Returns:
        ``{lower(email): AbsenceInfo}`` для каждого email с ``current_status``
        из ``{vacation, sick, business_trip}`` (``working`` не попадает).
    """
    normalized = [e.lower() for e in emails if e]
    if not normalized:
        return {}

    rows = (
        await db.execute(
            select(
                func.lower(User.email).label("email"),
                User.current_status,
                User.current_status_until,
            ).where(func.lower(User.email).in_(normalized))
        )
    ).all()

    out: dict[str, AbsenceInfo] = {}
    for row in rows:
        category = row.current_status
        if category not in ("vacation", "sick", "business_trip"):
            continue
        until = row.current_status_until
        out[row.email] = AbsenceInfo(
            category=category,
            start_date=until,
            end_date=until,
        )
    return out
