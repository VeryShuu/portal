"""Сопоставление ФИО исполнителя Directum с пользователем портала.

Клон :mod:`app.services.erp_sync.matcher` (модули независимы — erp может
меняться под свои задачи). Переиспользует чистые функции data-access-слоя
``app.api.users.users_repo``: точное совпадение → по словам в любом порядке
(ё→е, падежные окончания, раскладка клавиатуры).

Триаж:

* ``1`` кандидат → :class:`Matched`;
* ``>1`` → :class:`Ambiguous` (однофамильцы; НЕ уведомляем — в отчёт);
* ``0`` → :class:`Unmatched` (нет на портале — в отчёт; сюда же падают
  нестандартные исполнители вида «Капитан судна Н.Трубятчинский»).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.api.users.users_repo import find_by_full_name_exact, find_by_full_name_words
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Сколько кандидатов показать админу в отчёте при неоднозначности.
_MAX_AMBIGUOUS_CANDIDATES = 5


@dataclass
class Matched:
    """Однозначный матч (ровно 1 кандидат)."""

    user: User


@dataclass
class Ambiguous:
    """Несколько кандидатов на одно ФИО — уведомлять нельзя (не знаем кому)."""

    candidates: list[User]


@dataclass
class Unmatched:
    """На портале нет пользователя с таким ФИО."""


MatchResult = Matched | Ambiguous | Unmatched


async def match_performer(db: AsyncSession, fio: str) -> MatchResult:
    """Сопоставить ФИО исполнителя Directum с одним пользователем портала."""
    exact = await find_by_full_name_exact(db, fio)
    if len(exact) == 1:
        return Matched(user=exact[0])
    if len(exact) > 1:
        return Ambiguous(candidates=exact[:_MAX_AMBIGUOUS_CANDIDATES])

    words = await find_by_full_name_words(db, fio)
    if len(words) == 1:
        return Matched(user=words[0])
    if len(words) > 1:
        return Ambiguous(candidates=words[:_MAX_AMBIGUOUS_CANDIDATES])

    return Unmatched()


def candidate_summary(user: User) -> dict:
    """Компактное описание кандидата для отчёта админу (ambiguous-секция)."""
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "department": user.department,
    }
