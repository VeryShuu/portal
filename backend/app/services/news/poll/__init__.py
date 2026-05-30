"""News poll service package.

Раньше — монолитный ``app/services/news/poll.py`` (799 строк). Разложен
на подмодули по ответственности (см. ref.md, пункт 1.1):

- :mod:`._helpers` — константы, предикаты прав, преобразование datetime,
  фабрики ``HTTPException``, ``is_poll_closed``, ``_can_see_results``.
- :mod:`.queries` — read-only выборки: ``get_poll_by_news_id``,
  ``build_poll_public_response``, ``get_voters_list``.
- :mod:`.crud` — создание/обновление/удаление опросов и вопросов,
  закрытие/открытие.
- :mod:`.voting` — приём и отзыв голосов, валидация ответов,
  перерасчёт счётчиков.

Все публичные имена реэкспортированы из пакета — внешние импорты
``from app.services.news.poll import X`` остаются совместимыми.
"""

from __future__ import annotations

from ._helpers import (
    POLL_ALWAYS_EDITABLE,
    POLL_FROZEN_AFTER_VOTE,
    PRIVILEGED_ROLES,
    QUESTION_ALWAYS_EDITABLE,
    QUESTION_FROZEN_AFTER_VOTE,
    _aware,
    _bad,
    _can_see_results,
    _forbid,
    _is_privileged,
    is_poll_closed,
)
from .crud import (
    close_poll,
    create_poll,
    delete_poll,
    reopen_poll,
    update_poll,
)
from .queries import (
    build_poll_public_response,
    get_poll_by_news_id,
    get_voters_list,
)
from .voting import cast_vote, revoke_vote

__all__ = [
    "POLL_ALWAYS_EDITABLE",
    "POLL_FROZEN_AFTER_VOTE",
    "PRIVILEGED_ROLES",
    "QUESTION_ALWAYS_EDITABLE",
    "QUESTION_FROZEN_AFTER_VOTE",
    "_aware",
    "_bad",
    "_can_see_results",
    "_forbid",
    "_is_privileged",
    "build_poll_public_response",
    "cast_vote",
    "close_poll",
    "create_poll",
    "delete_poll",
    "get_poll_by_news_id",
    "get_voters_list",
    "is_poll_closed",
    "reopen_poll",
    "revoke_vote",
    "update_poll",
]
