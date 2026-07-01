"""Сборка истории переписки для исходящего helpdesk-письма.

Промышленный стандарт helpdesk-систем (Zammad/Freshdesk/Help Scout): исходящее
письмо заявителю несёт **историю переписки под reply-маркером** «ответьте выше
этой строки». Тогда:

* заявитель видит контекст прямо в почтовом клиенте;
* при ответе его почтовый клиент цитирует наш блок (ответ + маркер + история),
  а ``strip_quoted_reply`` (см. ``email_quote``) чётко режет по
  ``REPLY_MARKER_TOKEN`` → в ленте портала остаётся только чистый ответ.

Маркер ставится в ``_try_enqueue_outbound`` **между** телом ответа и историей
(см. ``app.api.helpdesk.tickets``).

Чистые функции — тестируются без БД (образец — ``email_quote``).
"""

from __future__ import annotations

import html
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.helpdesk import HelpdeskMessage

# Лимит предшествующих сообщений в истории: защита от гигантских писем в долгих
# тикетах. Берём «хвост» переписки (самые свежие), хронологически.
HISTORY_MAX_MESSAGES = 20

# Цвета inline-стилей истории (почтовые клиенты игнорируют CSS-классы — только
# inline-атрибуты, см. ``build_assigned_email_bodies``).
_HISTORY_BORDER = "#e0e0e0"
_HISTORY_TEXT = "#666"
_HISTORY_META = "#888"


def build_thread_history(
    messages: list[HelpdeskMessage],
    *,
    exclude_id: uuid.UUID,
    ticket_number: int,
) -> tuple[str, str]:
    """Собрать историю переписки для исходящего письма.

    Возвращает ``(plain, html)`` — два представления предшествующих публичных
    сообщений тикета (в хронологическом порядке), готовых к добавлению в тело
    письма **после** reply-маркера.

    Параметры:
        messages: все сообщения тикета (с ORM-relationship или прямым запросом).
        exclude_id: id текущего ответа агента (его тело уже в письме сверху).
        ticket_number: номер тикета (для заголовка блока истории).

    ``internal``-заметки в историю не попадают — они не видны заявителю.
    Если предшествующих публичных сообщений нет (первый ответ на заявку) —
    оба представления пустые (письмо = только ответ + маркер).
    """
    prior = [
        m
        for m in messages
        if m.id != exclude_id and m.visibility != "internal"
    ]
    # Хронологический порядок + лимит самых свежих.
    prior.sort(key=lambda m: m.created_at)
    if len(prior) > HISTORY_MAX_MESSAGES:
        prior = prior[-HISTORY_MAX_MESSAGES:]
    if not prior:
        return "", ""

    plain_parts: list[str] = [_history_header_plain(ticket_number)]
    html_parts: list[str] = [_history_header_html(ticket_number)]
    for m in prior:
        plain_parts.append(_message_block_plain(m))
        html_parts.append(_message_block_html(m))

    return "\n\n".join(plain_parts), "\n".join(html_parts)


# ── Plain-text ───────────────────────────────────────────────────────────────


def _history_header_plain(ticket_number: int) -> str:
    return f"=== История заявки [#TKT-{ticket_number}] ==="


def _message_block_plain(msg: HelpdeskMessage) -> str:
    """Классический email-цитатник: ``On {date}, {author} wrote:`` + ``>`` строки.

    Формат понятен всем почтовым клиентам и сам по себе является стандартным
    паттерном цитирования (Gmail/Outlook так оформляют ответы)."""
    when = _format_date(msg.created_at)
    who = _display_name(msg)
    body = (msg.body_text or "").strip()
    quoted = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    return f"От {who}, {when}:\n{quoted}"


# ── HTML ─────────────────────────────────────────────────────────────────────


def _history_header_html(ticket_number: int) -> str:
    return (
        f'<div style="margin-top:24px;padding-top:12px;'
        f'border-top:1px solid {_HISTORY_BORDER};'
        f'color:{_HISTORY_META};font-size:0.85em;'
        f'font-family:sans-serif;">'
        f"История заявки [#TKT-{ticket_number}]"
        "</div>"
    )


def _message_block_html(msg: HelpdeskMessage) -> str:
    """Inline-стилизованный блок одного сообщения истории.

    Использует ``body_html`` если есть (уже sanitized в БД), иначе экранированный
    ``body_text`` в ``<pre>``. Имя автора и дата — экранированы (пользовательские
    данные)."""
    when = html.escape(_format_date(msg.created_at))
    who = html.escape(_display_name(msg))
    direction_label = "←" if msg.direction == "inbound" else "→"
    body = _message_body_html(msg)
    return (
        f'<div style="margin:10px 0;padding:8px 12px;'
        f'border-left:3px solid {_HISTORY_BORDER};'
        f'font-family:sans-serif;">'
        f'<div style="color:{_HISTORY_META};font-size:0.85em;'
        f'margin-bottom:4px;">{direction_label} {who}, {when}</div>'
        f'<div style="color:{_HISTORY_TEXT};font-size:0.9em;">{body}</div>'
        "</div>"
    )


def _message_body_html(msg: HelpdeskMessage) -> str:
    """Тело сообщения в HTML: sanitized ``body_html`` или ``<pre>`` из plain."""
    if msg.body_html:
        return msg.body_html
    text = (msg.body_text or "").strip()
    return f"<pre>{html.escape(text)}</pre>"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _display_name(msg: HelpdeskMessage) -> str:
    return (msg.author_name or msg.author_email or "?").strip()


def _format_date(dt: datetime) -> str:
    """Локализованное представление даты для заголовка блока истории."""
    return dt.strftime("%d.%m.%Y %H:%M")
