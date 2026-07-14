"""Сборка истории переписки для исходящего helpdesk-письма.

Промышленный стандарт helpdesk-систем (Zammad/Freshdesk/Help Scout): исходящее
письмо заявителю несёт **историю переписки под reply-маркером** «Ответьте выше
этой линии». Тогда:

* заявитель видит контекст прямо в почтовом клиенте;
* при ответе его почтовый клиент цитирует наш блок (ответ + маркер + история),
  а ``strip_quoted_reply`` (см. ``email_quote``) чётко режет по
  ``REPLY_MARKER_TOKEN`` → в ленте портала остаётся только чистый ответ.

Маркер ставится в ``_try_enqueue_outbound`` **между** телом ответа и историей
(см. ``app.api.helpdesk.tickets``), обёрнутыми в единый шаблон
``email_template.render_reply_email``. HTML-блоки истории рендерит
``email_template.render_history_block`` (минималистичный таймлайн: accent/grey
имя + левая цветная полоса + подпись «Исполнитель»).

Чистые функции — тестируются без БД (образец — ``email_quote``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from app.services.helpdesk.email_template import render_history_block

if TYPE_CHECKING:
    from app.models.helpdesk import HelpdeskMessage

# Лимит предшествующих сообщений в истории: защита от гигантских писем в долгих
# тикетах. Берём «хвост» переписки (самые свежие), хронологически.
HISTORY_MAX_MESSAGES = 20


def build_thread_history(
    messages: list[HelpdeskMessage],
    *,
    exclude_id: uuid.UUID,
    ticket_number: int,
    assignee_user_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Собрать историю переписки для исходящего письма.

    Возвращает ``(plain, html)`` — два представления предшествующих публичных
    сообщений тикета (в хронологическом порядке), готовых к добавлению в тело
    письма **после** reply-маркера. Заголовок HTML-секции истории («Предыдущие
    сообщения») ставит шаблон ``render_reply_email`` — здесь не дублируется.

    Параметры:
        messages: все сообщения тикета (с ORM-relationship или прямым запросом).
        exclude_id: id текущего ответа агента (его тело уже в письме сверху).
        ticket_number: номер тикета (для заголовка plain-истории).
        assignee_user_id: назначенный специалист тикета — для подписи «Исполнитель»
            в блоках истории (если автор сообщения = назначенный специалист).
            Сравнение UUID внутри ``render_history_block``, без доп. запросов.

    ``internal``-заметки в историю не попадают — они не видны заявителю.
    Если предшествующих публичных сообщений нет (первый ответ на заявку) —
    оба представления пустые (письмо = только ответ, без разделителя/истории).
    """
    prior = [m for m in messages if m.id != exclude_id and m.visibility != "internal"]
    # Сортировка по возрастанию для корректного лимита свежих (хвост списка),
    # затем реверс — в письме история идёт NEWEST→OLDEST: ответ агента вверху,
    # сразу под разделителем — ближайшее предшествующее сообщение, самое старое
    # внизу. Это даёт continuity (ответ → назад во времени) и соответствует
    # стандарту Zammad/Freshdesk.
    prior.sort(key=lambda m: m.created_at)
    if len(prior) > HISTORY_MAX_MESSAGES:
        prior = prior[-HISTORY_MAX_MESSAGES:]
    prior.reverse()
    if not prior:
        return "", ""

    plain_parts: list[str] = [_history_header_plain(ticket_number)]
    html_parts: list[str] = []
    for m in prior:
        plain_parts.append(_message_block_plain(m))
        # HTML-блок — таймлайн (accent/grey имя + левая полоса, подпись «Исполнитель»
        # при совпадении автора с назначенным специалистом).
        html_parts.append(render_history_block(m, assignee_user_id=assignee_user_id))

    return "\n\n".join(plain_parts), "\n".join(html_parts)


# ── Plain-text ───────────────────────────────────────────────────────────────


def _history_header_plain(ticket_number: int) -> str:
    return f"=== История заявки [#TKT-{ticket_number}] ==="


def _message_block_plain(msg: HelpdeskMessage) -> str:
    """Классический email-цитатник: ``От {author}, {date}:`` + ``>`` строки.

    Формат понятен всем почтовым клиентам и сам по себе является стандартным
    паттерном цитирования (Gmail/Outlook так оформляют ответы)."""
    when = _format_date(msg.created_at)
    who = _display_name(msg)
    body = (msg.body_text or "").strip()
    quoted = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    return f"От {who}, {when}:\n{quoted}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _display_name(msg: HelpdeskMessage) -> str:
    return (msg.author_name or msg.author_email or "?").strip()


def _format_date(dt: datetime) -> str:
    """Локализованное представление даты в портала-tz (делегирует в
    ``email_template._format_date`` — единая конвертация UTC→tz для писем)."""
    from app.services.helpdesk.email_template import _format_date as _fmt

    return _fmt(dt)
