"""Вычисляемый статус присутствия сотрудника (``users.current_status``).

Источник истины — только ERP (таблица ``erp_absences``). Ручной выбор статуса
убран (миграция 093 дропнула ``users.presence_status``).

7 ERP-kinds схлопываются в 4 категории для UI (детальный kind остаётся в
``erp_absences`` и показывается в карточке профиля):

================  ==============================================================
категория         ERP kinds
================  ==============================================================
``working``       нет активной absence (сегодня ∈ [start_date, end_date])
``vacation``      ``vacation_main`` / ``vacation_extra`` / ``unpaid_leave`` /
                  ``day_off_paid`` / ``day_off_unpaid``
``sick``          ``sick``
``business_trip`` ``business_trip``
================  ==============================================================

Приоритет при пересечении нескольких одновременных отсутствий:
``sick`` > ``vacation`` > ``business_trip`` (больной в командировке → показываем
«болезнь»). ``current_status_until`` = ``end_date`` приоритетной записи.

Пересчёт запускается:
* в конце ``absences_importer.run_absences_import`` — для затронутых ``user_ids``
  (включая исчезнувших из отчёта, иначе они останутся в старом статусе);
* ежедневным cron'ом ``recompute_daily_presence_status`` — полный пересчёт для
  перехода дат (вчерашний отпуск кончился → ``working``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

# Канонический tuple категорий статуса (синхронизирован с CHECK
# ck_users_current_status в миграции 093 и UserStatusCategory во фронтенде).
ABSENCE_CATEGORY_VALUES: tuple[str, ...] = ("working", "vacation", "sick", "business_trip")

# Маппинг canonical ERP-kind → категория статуса.
_KIND_TO_CATEGORY: dict[str, str] = {
    "vacation_main": "vacation",
    "vacation_extra": "vacation",
    "unpaid_leave": "vacation",
    "day_off_paid": "vacation",
    "day_off_unpaid": "vacation",
    "sick": "sick",
    "business_trip": "business_trip",
}

# Приоритет категории при пересечении нескольких одновременных отсутствий.
# Меньше = выше приоритет (больной в командировке → sick).
_CATEGORY_PRIORITY: dict[str, int] = {
    "sick": 0,
    "vacation": 1,
    "business_trip": 2,
    "working": 3,
}


def kind_to_category(kind: str) -> str:
    """Вернуть категорию статуса (``working``/``vacation``/``sick``/``business_trip``).

    Неизвестный kind → ``working`` (защита от будущих значений ERP).
    """
    return _KIND_TO_CATEGORY.get(kind, "working")


def category_priority(category: str) -> int:
    """Приоритет категории для сортировки «какую показать при пересечении»."""
    return _CATEGORY_PRIORITY.get(category, _CATEGORY_PRIORITY["working"])


# Параметризованный SQL пересчёта. ``:today`` bind, ``:user_ids`` — опциональный
# массив UUID (NULL = полный пересчёт со сбросом остальных в working).
# DISTINCT ON (user_id) + ORDER BY user_id, priority — оставляет одну
# (приоритетную) запись на пользователя. CTE covers как presence
# (активные absence), так и reset (для полного режима — user'ы без активных
# absence сбрасываются в working).
# nosec B608 — параметризованный SQL без интерполяции пользовательских данных.
_RECOMPUTE_SQL = text(
    """
    WITH active AS (
        SELECT DISTINCT ON (ea.user_id)
               ea.user_id,
               ea.end_date,
               CASE ea.kind
                   WHEN 'sick' THEN 'sick'
                   WHEN 'business_trip' THEN 'business_trip'
                   ELSE 'vacation'
               END AS category,
               CASE ea.kind
                   WHEN 'sick' THEN 0
                   WHEN 'business_trip' THEN 2
                   ELSE 1
               END AS priority
        FROM erp_absences ea
        WHERE ea.start_date <= CAST(:today AS date)
          AND ea.end_date >= CAST(:today AS date)
        ORDER BY ea.user_id, priority ASC, ea.end_date DESC
    )
    UPDATE users u
    SET current_status = COALESCE(a.category, 'working'),
        current_status_until = a.end_date
    FROM active a
    WHERE u.id = a.user_id
      AND (:user_ids IS NULL OR u.id = ANY(CAST(:user_ids AS UUID[])))
    """
)


async def recompute_current_status(
    db: AsyncSession,
    user_ids: Iterable[uuid.UUID] | None,
    *,
    today: date | None = None,
) -> int:
    """Пересчитать ``users.current_status`` / ``current_status_until``.

    Args:
        db: активная сессия (flush/commit выполняется вызывающей стороной).
        user_ids: ограничение множества пользователей. ``None`` — полный
            пересчёт всех пользователей с любой ``erp_absences``-записью.
            Внимание: в режиме ``None`` пользователи без активной absence,
            у которых ранее был статус, **не сбрасываются** этим запросом
            (UPDATE только по JOIN с active). Для сброса используйте
            :func:`reset_users_to_working` или полный cron-режим ниже.
        today: опорная дата (по умолчанию ``date.today()``).

    Returns:
        Количество обновлённых строк (rowcount).
    """
    ref_day = today if today is not None else date.today()
    ids_param: list[str] | None = None
    if user_ids is not None:
        ids_param = [str(uid) for uid in user_ids]

    result = await db.execute(
        _RECOMPUTE_SQL,
        {"today": ref_day.isoformat(), "user_ids": ids_param},
    )
    updated = int(cast(CursorResult, result).rowcount or 0)
    logger.info(
        "erp_sync.absences_status.recomputed",
        updated=updated,
        scoped=user_ids is not None,
        today=ref_day.isoformat(),
    )
    return updated


_RESET_SQL = text(
    """
    UPDATE users
    SET current_status = 'working',
        current_status_until = NULL
    WHERE id = ANY(CAST(:user_ids AS UUID[]))
      AND NOT EXISTS (
          SELECT 1 FROM erp_absences ea
          WHERE ea.user_id = users.id
            AND ea.start_date <= CAST(:today AS date)
            AND ea.end_date >= CAST(:today AS date)
      )
    """
)


async def reset_users_to_working(
    db: AsyncSession,
    user_ids: Iterable[uuid.UUID],
    *,
    today: date | None = None,
) -> int:
    """Сбросить перечисленных пользователей без активной absence в ``working``.

    Используется импортёром для user'ов, чьи строки исчезли из отчёта ERP:
    после full-replace DELETE их ``current_status`` остаётся устаревшим, а JOIN
    с ``active`` их больше не покрывает. Этот запрос явно сбрасывает их.
    """
    ref_day = today if today is not None else date.today()
    ids_list = [str(uid) for uid in user_ids]
    if not ids_list:
        return 0
    result = await db.execute(
        _RESET_SQL,
        {"user_ids": ids_list, "today": ref_day.isoformat()},
    )
    updated = int(cast(CursorResult, result).rowcount or 0)
    logger.info(
        "erp_sync.absences_status.reset_to_working",
        updated=updated,
        today=ref_day.isoformat(),
    )
    return updated
