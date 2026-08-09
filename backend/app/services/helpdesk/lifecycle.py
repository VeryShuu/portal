"""Status-machine for helpdesk tickets (ТЗ §4.2).

Чистая логика переходов без побочных эффектов и БД — её удобно
unit-тестировать (см. ``tests/unit/test_helpdesk_lifecycle.py``). Рантайм-окна
(``HELPDESK_REOPEN_WINDOW_DAYS`` и т.д.) лежат в ``app/core/constants.py``;
правила reopen из ``closed`` по времени применяются здесь.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.constants import HELPDESK_REOPEN_WINDOW_DAYS
from app.schemas.helpdesk import (
    AGENT_SETTABLE_STATUSES,
    REQUESTER_REOPEN_STATUSES,
    HelpdeskStatus,
)

# Re-export для обратной совместимости с существующими импортами
# (`from app.services.helpdesk.lifecycle import AGENT_SETTABLE_STATUSES`).
# Единый источник истины — ``app.schemas.helpdesk`` (audit [H7]).
__all__ = [
    "AGENT_SETTABLE_STATUSES",
    "REQUESTER_REOPEN_STATUSES",
    "IllegalTransitionError",
    "TransitionResult",
    "agent_outbound_reply",
    "agent_set_status",
    "closed_reopen_eligible",
    "requester_reply",
    "requester_reply_on_closed",
]


class IllegalTransitionError(Exception):
    """Невозможный переход статус-машины. ``current``/``allowed`` содержат
    диагностическую информацию, которую роутер транслирует в 409."""

    def __init__(self, current: str, allowed: list[str]) -> None:
        self.current = current
        self.allowed = allowed
        super().__init__(f"Illegal transition from {current}; allowed: {allowed}")


@dataclass(frozen=True)
class TransitionResult:
    status: str
    cleared_closed: bool = False
    set_closed: bool = False


def agent_set_status(current: str, target: str) -> TransitionResult:
    """Ручной переход статуса агентом/админом (PATCH /status).

    Разрешённые переходы (ТЗ §4.2.1):
    * любой → ``open``/``pending`` (из ``new`` — взятие в работу / ожидание);
    * любой активный → ``closed`` (агент завершил работу; ``closed`` = единый
      финал, тикет уходит в архив по ``HELPDESK_ARCHIVE_AFTER_DAYS``);
    * ``closed`` → ``open`` — это reopen, отдельный endpoint (не здесь);
    * ``new`` → ``closed`` напрямую разрешён (краевые случаи, админ может сразу
      закрыть спам).

    ``resolved`` упразднён (миграция 079) — двухфазное закрытие убрано,
    ``closed`` теперь единственный финальный статус.

    Переход в текущий статус — no-op (idempotent PATCH).
    """
    if target not in AGENT_SETTABLE_STATUSES:
        raise IllegalTransitionError(current=current, allowed=sorted(AGENT_SETTABLE_STATUSES))
    if current == target:
        return TransitionResult(status=current)

    set_closed = target == HelpdeskStatus.closed
    return TransitionResult(status=target, set_closed=set_closed)


def requester_reply(current: str) -> TransitionResult:
    """Ответ инициатора (web или email). Реопенит ``pending`` в ``open`` без
    окна; ``new``/``open``/``closed`` не меняет (``closed`` реопенится только в
    окне через отдельный путь — см. ``requester_reply_on_closed``)."""
    if current in REQUESTER_REOPEN_STATUSES:
        return TransitionResult(status=HelpdeskStatus.open)
    return TransitionResult(status=current)


def closed_reopen_eligible(closed_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Можно ли авто-реопенуть ``closed`` тикет ответом клиента.

    Окно ``HELPDESK_REOPEN_WINDOW_DAYS`` отсчитывается от ``closed_at``
    (ТЗ §4.2). Если ``closed_at`` неизвестен (``None``) — окно считаем
    истекшим (безопасный дефолт: не реопенить вслепую)."""
    if closed_at is None:
        return False
    now = now or datetime.now(UTC)
    return closed_at + timedelta(days=HELPDESK_REOPEN_WINDOW_DAYS) >= now


def requester_reply_on_closed(
    closed_at: datetime | None, *, now: datetime | None = None
) -> TransitionResult:
    """Ответ клиента по ``closed``-тикету. В окне → reopen в ``open`` (с
    очисткой ``closed_*``); вне окна — статус не меняется (в IMAP-потоке это
    создаст новый тикет, но веб-инициатор просто не сможет ответить — у него
    нет UI; для email это решается на этапе 5)."""
    if closed_reopen_eligible(closed_at, now=now):
        return TransitionResult(status=HelpdeskStatus.open, cleared_closed=True)
    return TransitionResult(status=HelpdeskStatus.closed)


def agent_outbound_reply(current: str) -> TransitionResult:
    """Публичный ответ агента → ``pending`` (ждём клиента).

    ТЗ §4.2.1: ``new`` → ``pending`` (с авто-назначением), ``open`` →
    ``pending``, ``pending`` → ``pending``. Internal-заметки статус не меняют
    (обрабатывается в сервисе отдельно)."""
    return TransitionResult(status=HelpdeskStatus.pending)
