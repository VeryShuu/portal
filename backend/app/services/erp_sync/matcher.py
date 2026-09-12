"""Сопоставление ФИО из ERP-выгрузки с пользователями портала.

Переиспует готовый FIO-матчер из ``app.api.users.users_repo`` (его уже юзает
модуль meetings — ``find_by_full_name_exact`` / ``find_by_full_name_words``).
Эти функции — чистая data-access-логика, не привязаны к meetings.

Pipeline (per-row):

1. ``find_by_full_name_exact`` — точное CI-совпадение (с ё→е и раскладкой).
2. Если 0 → ``find_by_full_name_words`` — по словам в любом порядке
   («Артем Богославский» найдёт «Богославский Артем Петрович»).
3. Triage по ``len(matches)``:

   * ``1`` → :class:`Matched` (однозначный матч, можно обновлять).
   * ``>1`` → :class:`Ambiguous` (несколько кандидатов — полный однофамилец;
     НЕ обновляем, в отчёт).
   * ``0`` → :class:`Unmatched` (нет на портале; в отчёт).

НЕ делает UPDATE — только возвращает результат. Запись в БД — забота
:mod:`importer`, чтобы matcher оставался чистой (тестируемой без транзакции).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.api.users.users_repo import find_by_full_name_exact, find_by_full_name_words
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Сколько кандидатов показать админу в отчёте при неоднозначности.
# Полный список может быть длинным (однофамильцы) — обрезаем.
_MAX_AMBIGUOUS_CANDIDATES = 5


@dataclass
class Matched:
    """Однозначный матч (ровно 1 кандидат)."""

    user: User


@dataclass
class Ambiguous:
    """Несколько кандидатов на одно ФИО — обновлять нельзя."""

    candidates: list[User]


@dataclass
class Unmatched:
    """На портале нет пользователя с таким ФИО."""


MatchResult = Matched | Ambiguous | Unmatched


async def match_row(db: AsyncSession, fio: str) -> MatchResult:
    """Сопоставить ФИО с одним пользователем портала.

    Args:
        db: async-сессия БД.
        fio: ФИО из ERP (display-форма, с заглавных; нормализацию делает
            ``users_repo`` внутри — lower + ё→е + раскладка).

    Returns:
        :class:`Matched` / :class:`Ambiguous` / :class:`Unmatched`.
    """
    # 1. Точное совпадение — самый частый и быстрый путь.
    exact = await find_by_full_name_exact(db, fio)
    if len(exact) == 1:
        return Matched(user=exact[0])
    if len(exact) > 1:
        return Ambiguous(candidates=exact[:_MAX_AMBIGUOUS_CANDIDATES])

    # 2. Нечёткий матч по словам (разный порядок, с отчеством/без).
    words = await find_by_full_name_words(db, fio)
    if len(words) == 1:
        return Matched(user=words[0])
    if len(words) > 1:
        return Ambiguous(candidates=words[:_MAX_AMBIGUOUS_CANDIDATES])

    return Unmatched()


def candidate_summary(user: User) -> dict:
    """Компактное описание кандидата для отчёта админу (ambiguous-секция).

    Содержит id, ФИО, отдел — достаточно, чтобы админ понял, кто это, и
    разрешил коллизию вручную.
    """
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "department": user.department,
    }
