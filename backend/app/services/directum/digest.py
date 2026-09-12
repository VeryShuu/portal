"""Дайджест «Просроченные задачи» для личного чата Matrix.

Один сотрудник = одно сообщение со списком всех его просроченных задач
(решение зафиксировано — не спамим сообщением на задачу). Возвращает
``(plain, formatted_body)``: plain — обязательный fallback тела сообщения,
``formatted_body`` — HTML из whitelist'а Matrix (``<b>``, ``<br>``) с
``html.escape`` на каждом значении (тема задачи — пользовательские данные).

Язык — русский (как уведомления MAX-бота и email-отчёты), не через
frontend-i18n: получатель — сотрудник портала, мастер-локаль ru.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.directum.odata import OverdueAssignment

_MAX_TASKS_IN_DIGEST = 50  # защита от гигантских сообщений (Matrix-лимит ~32 КБ)


def build_overdue_digest(tasks: list[OverdueAssignment], *, now: datetime) -> tuple[str, str]:
    """``(plain, html)`` дайджест просроченных задач одного сотрудника."""
    visible = tasks[:_MAX_TASKS_IN_DIGEST]
    hidden = len(tasks) - len(visible)

    plain_lines = [f"🔴 Просроченные задачи в Directum — {len(tasks)}", ""]
    html_parts = [f"<b>🔴 Просроченные задачи в Directum — {len(tasks)}</b><br><br>"]
    for i, task in enumerate(visible, start=1):
        overdue = _overdue_label(task.deadline, now)
        subject = task.subject or "(без темы)"
        plain_lines.append(f"{i}. {subject}")
        plain_lines.append(f"   Срок: {_fmt_dt(task.deadline)} — {overdue}")
        html_parts.append(
            f"{i}. <b>{html.escape(subject)}</b><br>"
            f"Срок: {_fmt_dt(task.deadline)} — {html.escape(overdue)}<br><br>"
        )
    if hidden > 0:
        plain_lines.append(f"… и ещё {hidden} (см. Directum)")
        html_parts.append(f"… и ещё {hidden} (см. Directum)<br>")
    plain_lines.append("")
    plain_lines.append("— портал, автоуведомление")
    return "\n".join(plain_lines), "".join(html_parts)


def _fmt_dt(value: datetime) -> str:
    """Формат срока в зоне значении (Directum отдаёт +03:00)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


def _overdue_label(deadline: datetime, now: datetime) -> str:
    """«просрочено на N дн.» / «срок истёк сегодня» для одной задачи."""
    days = (now - deadline).days
    if days < 1:
        return "срок истёк сегодня"
    return f"просрочено на {days} дн."
