"""Единый HTML-шаблон исходящих helpdesk-писем (ответ агента + системные).

Промышленный паттерн (Zammad/Freshdesk/Help Scout): письмо заявителю —
брендированный шаблон с шапкой, читаемым блоком ответа, заметным
reply-разделителем (точка отсечения цитаты при ответе), alternating-историей
и футером. Референс в проекте — ``news/email_share.py`` (табличная вёрстка
600px, inline-стили — почтовые клиенты игнорируют CSS-классы).

Все user-facing данные экранируются через ``html.escape`` (паттерн meetings/news).

Шаблон применяется в:
* ``_try_enqueue_outbound`` (ответ агента + история) → ``render_reply_email``;
* ``build_assigned_email_bodies`` (назначение ответственного) → ``render_system_email``.

Reply-маркеры (``build_reply_marker_*``) переносятся сюда из ``email_quote``:
токен ``REPLY_MARKER_TOKEN`` сохраняется в тексте разделителя — ``strip_quoted_html``
продолжает его ловить (открыающий тег перед текстом-маркером, см. regex
``_OWN_MARKER_HTML_RE``).

Чистые функции — тестируются без БД.
"""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket

# ── Палитра (согласована с news/meetings) ────────────────────────────────────

_ACCENT = "#143a66"  # brand-полоса, border-left специалиста
_TEXT = "#1a1a1a"  # основной текст (ответ агента)
_TEXT_HISTORY = "#333"  # текст истории (чуть мягче основного)
_META = "#888"  # даты, футер
_BORDER = "#e0e0e0"
_BG_INBOUND = "#f5f5f5"  # фон сообщения заявителя в истории
_BG_OUTBOUND = "#ffffff"  # фон сообщения специалиста
_BADGE_AGENT_BG = "#1d4e89"  # бейдж «Специалист» — насыщенный синий (pill)
_BADGE_AGENT_TEXT = "#ffffff"
_BADGE_REQUESTER_BG = "#6b7280"  # бейдж «Заявитель» — насыщенный серый (pill)
_BADGE_REQUESTER_TEXT = "#ffffff"
_FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, "
    "'Helvetica Neue', Arial, sans-serif"
)
_WIDTH = 640

# ``REPLY_MARKER_TOKEN`` и ``build_reply_marker_*`` — единый источник истины в
# ``email_quote`` (там же regex детекции при ответе заявителя). Шаблон только
# использует их. Импорт после объявления констант-палитры (noqa E402).
from app.services.helpdesk.email_quote import (  # noqa: E402
    build_reply_marker_html,
    build_reply_marker_plain,
)

# ── Шапка / футер ────────────────────────────────────────────────────────────


def _esc(value: str | None) -> str:
    """Экранирование пользовательских данных (паттерн news ``_esc``)."""
    return html.escape(value or "", quote=True)


def _header_html(ticket_number: int, subject: str) -> str:
    """Шапка письма: brand-полоса + номер заявки + тема."""
    subject_esc = _esc(subject)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"'
        ' style="border-collapse:collapse;">'
        "  <tr>"
        f'    <td style="background:{_ACCENT};padding:16px 20px;font-family:{_FONT};">'
        '      <div style="color:#ffffff;font-size:13px;font-weight:600;'
        'letter-spacing:0.5px;text-transform:uppercase;opacity:0.85;">'
        f"        Заявка №TKT-{ticket_number}"
        "      </div>"
        '      <div style="color:#ffffff;font-size:18px;font-weight:600;margin-top:4px;">'
        f"        {subject_esc}"
        "      </div>"
        "    </td>"
        "  </tr>"
        "</table>"
    )


def _footer_html(portal_url: str | None) -> str:
    """Футер: ссылка на портал + «автоматическое уведомление»."""
    if portal_url:
        link = _esc(portal_url)
        portal_line = (
            '<div style="margin-bottom:6px;">'
            f'<a href="{link}" style="color:{_ACCENT};'
            'text-decoration:none;">Открыть заявку в портале</a>'
            "</div>"
        )
    else:
        portal_line = ""
    return f"""\
<div style="margin-top:32px;padding-top:20px;border-top:1px solid {_BORDER};font-family:{_FONT};">
  {portal_line}
  <div style="color:{_META};font-size:12px;">
    Это автоматическое уведомление портала техподдержки. Не отвечайте напрямую на email отправителя.
  </div>
</div>"""


def _wrap(content: str, *, ticket_number: int, subject: str, portal_url: str | None) -> str:
    """Обёртка: внешний контейнер 600px + шапка + контент + футер."""
    return (
        f'<div style="font-family:{_FONT};color:{_TEXT};font-size:15px;line-height:1.55;">'
        f'<table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;max-width:{_WIDTH}px;margin:0 auto;">'
        f"{_header_html(ticket_number, subject)}"
        f'<tr><td style="padding:28px;">{content}{_footer_html(portal_url)}</td></tr>'
        "</table>"
        "</div>"
    )


# ── Блок истории ────────────────────────────────────────────────────────────


def render_history_block(msg: HelpdeskMessage) -> str:
    """Один блок истории как «карточка»: видимые отступы, рамка, цветной
    бейдж-роль. Чёткое визуальное разделение между сообщениями (вместо
    слитного alternating-фона).

    * inbound (от заявителя) — серый фон ``#f5f5f5``, бейдж «Заявитель» (серый pill).
    * outbound (от специалиста) — белый фон, accent border-left, бейдж «Специалист» (синий pill).
    """
    is_inbound = msg.direction == "inbound"
    who = _esc(msg.author_name or msg.author_email or "?")
    when = _esc(_format_date(msg.created_at))
    role_label, badge_bg, badge_text = (
        ("Заявитель", _BADGE_REQUESTER_BG, _BADGE_REQUESTER_TEXT)
        if is_inbound
        else ("Специалист", _BADGE_AGENT_BG, _BADGE_AGENT_TEXT)
    )
    bg = _BG_INBOUND if is_inbound else _BG_OUTBOUND
    border_left = "" if is_inbound else f"border-left:3px solid {_ACCENT};"
    body = _message_body_html(msg)
    return (
        # Карточка: margin 20px между блоками, padding 16px, рамка + тень,
        # скруглённые углы 8px.
        f'<div style="margin:20px 0;padding:16px 18px;background:{bg};'
        f"{border_left}border:1px solid {_BORDER};border-radius:8px;"
        f'box-shadow:0 1px 2px rgba(0,0,0,0.05);font-family:{_FONT};">'
        # Шапка блока: имя + цветной pill-бейдж роли + дата.
        f'<div style="margin-bottom:12px;font-size:13px;">'
        f'<span style="font-weight:600;color:{_TEXT_HISTORY};">{who}</span>'
        # Pill-бейдж: больше padding, скругление 10px (pill-форма), разделитель-пробел.
        f' <span style="display:inline-block;margin:0 6px;padding:2px 9px;'
        f"border-radius:10px;background:{badge_bg};color:{badge_text};"
        f"font-size:11px;font-weight:600;text-transform:uppercase;"
        f'letter-spacing:0.3px;">{role_label}</span>'
        f'<span style="color:{_META};">{when}</span>'
        "</div>"
        # Тело: отделено тонкой разделительной линией сверху для читаемости.
        f'<div style="padding-top:8px;border-top:1px solid {_BORDER};'
        f'color:{_TEXT_HISTORY};font-size:14px;line-height:1.55;">{body}</div>'
        # Вложения: чипы-ссылки (как в вебе), абсолютные URL.
        f"{_attachments_html(msg)}"
        "</div>"
    )


def _message_body_html(msg: HelpdeskMessage) -> str:
    """Тело сообщения: sanitized ``body_html`` или ``<div>`` из plain (не ``<pre>``,
    чтобы не было моноширинного «код»-вида)."""
    if msg.body_html:
        return msg.body_html
    text = (msg.body_text or "").strip()
    if not text:
        return ""
    escaped = _esc(text)
    # Переносы строк → <br> (plain текст сохраняет структуру).
    return f'<div style="white-space:pre-wrap;">{escaped}</div>'


def _attachments_html(msg: HelpdeskMessage) -> str:
    """Блок вложений сообщения: чипы-ссылки на скачивание (как в веб-версии).
    Делегирует в ``_attachments_list_html`` (общая логика для msg и списка)."""
    return _attachments_list_html(getattr(msg, "attachments", None) or [])


def _attachments_list_html(atts: list | None) -> str:
    """Чипы-ссылки вложений (абсолютные URL). Пусто если нет вложений.

    Ссылки абсолютные (``{portal_base_url}/api/v1/helpdesk/attachments/{id}``) —
    почтовый клиент не резолвит относительные пути."""
    if not atts:
        return ""
    base = _portal_base_url()
    chips: list[str] = []
    for a in atts:
        name = _esc(getattr(a, "original_name", None) or "файл")
        url = f"{base}/api/v1/helpdesk/attachments/{getattr(a, 'id', '')}"
        chips.append(
            f'<a href="{url}" style="display:inline-block;margin:4px 6px 0 0;'
            f"padding:4px 10px;background:#fff;border:1px solid {_BORDER};"
            f"border-radius:6px;font-size:12px;color:{_ACCENT};"
            f'text-decoration:none;">📎 {name}</a>'
        )
    return f'<div style="margin-top:10px;">{"".join(chips)}</div>'


def _format_date(dt: object) -> str:
    """Локализованное представление даты в часовом поясе портала.

    ``created_at`` хранится как UTC (``TIMESTAMPTZ``). Браузер в веб-версии
    конвертирует в локальное время пользователя (через ``toLocaleString``); в
    письме заявитель видит голое время из БД → рассинхрон (UTC vs локальное).
    Читаем ``timezone`` из runtime ``system_settings`` (default ``Europe/Moscow``,
    меняется через Admin UI) и конвертируем через ``ZoneInfo``. Совпадает с
    поведением meetings (``recurrence.py``) и системы в целом."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    if not isinstance(dt, datetime):
        return str(dt)
    tz_name = _portal_timezone()
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = ZoneInfo("Europe/Moscow")
    # Если dt naive — считаем UTC (на случай тестовых заглушек без tzinfo).
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone(local_tz).strftime("%d.%m.%Y %H:%M")


def _portal_timezone() -> str:
    """timezone из runtime system_settings (default Europe/Moscow)."""
    try:
        from app.core.system_config import load_system_settings

        return load_system_settings().timezone or "Europe/Moscow"
    except Exception:
        return "Europe/Moscow"


def _portal_base_url() -> str:
    """Базовый URL портала из runtime system_settings (default
    https://portal.company.local). Нужен для переписывания относительных
    img-src (``/api/...``) в абсолютные в письмах — почтовый клиент не
    резолвит относительные пути."""
    try:
        from app.core.system_config import load_system_settings

        url = (load_system_settings().portal_base_url or "").rstrip("/")
        return url or "https://portal.company.local"
    except Exception:
        return "https://portal.company.local"


# Относительные src: ``/api/...``, ``/static/...`` (без схемы/хоста). В письме
# почтовый клиент их не резолвит → картинка не грузится. Переписываем на
# абсолютные ``{portal_base_url}/api/...``. Внешние http(s):// и data: не трогаются.
_REL_SRC_RE = re.compile(r'(src=["\'])(/[^"\']+)(["\'])', re.IGNORECASE)


def _absolutize_img_src(html: str) -> str:
    """Переписать относительные ``src="/..."`` на абсолютные с ``portal_base_url``.

    Применяется ко всему HTML письма (ответ агента + история): в вебе src
    относительные (same-origin), но в письме почтовому клиенту нужен полный URL.
    Внешние ``http(s)://``/``data:``/``cid:`` не трогаются.
    """
    if not html:
        return html
    base = _portal_base_url()
    return _REL_SRC_RE.sub(lambda m: f"{m.group(1)}{base}{m.group(2)}{m.group(3)}", html)


# ── Главные точки: render_reply_email / render_system_email ──────────────────


def render_reply_email(
    *,
    ticket: HelpdeskTicket,
    agent_body_html: str,
    agent_body_text: str,
    history_html: str,
    history_plain: str,
    portal_url: str | None = None,
    message_author: str = "",
    message_created_at: object | None = None,
    message_attachments: list | None = None,
) -> tuple[str, str]:
    """Обёртка для письма-ответа агента: шапка + ответ + разделитель + история + футер.

    Возвращает ``(html, plain)``. ``history_*`` пустые → разделитель + заголовок
    истории не добавляются (первый ответ на заявку — истории ещё нет).
    """
    has_history = bool(history_html.strip())
    marker_html = build_reply_marker_html(ticket.number)
    marker_plain = build_reply_marker_plain(ticket.number)
    reply_date = _format_date(message_created_at) if message_created_at is not None else ""
    # Переписать относительные img-src на абсолютные (веб-вид → почта): без этого
    # картинки из body агента и истории (src="/api/...") не грузятся в письме.
    agent_body_html = _absolutize_img_src(agent_body_html)
    history_html = _absolutize_img_src(history_html)

    body_html = (
        # Ответ агента — карточка (как блоки истории), с явным заголовком,
        # чтобы он не прилипал к шапке и был визуально выделен.
        f'<div style="padding:16px 18px;background:{_BG_OUTBOUND};'
        f"border-left:3px solid {_ACCENT};border:1px solid {_BORDER};"
        f"border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,0.05);"
        f'font-family:{_FONT};margin-bottom:8px;">'
        f'<div style="margin-bottom:12px;font-size:13px;">'
        f'<span style="font-weight:600;color:{_TEXT_HISTORY};">'
        f"{_esc(message_author)}</span>"
        f' <span style="display:inline-block;margin:0 6px;padding:2px 9px;'
        f"border-radius:10px;background:{_BADGE_AGENT_BG};"
        f"color:{_BADGE_AGENT_TEXT};font-size:11px;font-weight:600;"
        f'text-transform:uppercase;letter-spacing:0.3px;">Специалист</span>'
        f'<span style="color:{_META};">{_esc(reply_date)}</span>'
        "</div>"
        f'<div style="padding-top:8px;border-top:1px solid {_BORDER};'
        f'color:{_TEXT};font-size:15px;line-height:1.6;">{agent_body_html}</div>'
        # Вложения ответа агента: чипы-ссылки, абсолютные URL.
        f"{_attachments_list_html(message_attachments)}"
        "</div>"
    )
    body_plain = agent_body_text

    if has_history:
        body_html += marker_html
        body_html += (
            f'<div style="margin-top:24px;padding-top:20px;'
            f'border-top:1px solid {_BORDER};font-family:{_FONT};">'
            f'<div style="color:{_META};font-size:13px;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:20px;">'
            "Предыдущие сообщения"
            "</div>"
            f"{history_html}"
            "</div>"
        )
        body_plain += marker_plain + "\n" + history_plain

    html_out = _wrap(
        body_html,
        ticket_number=ticket.number,
        subject=ticket.subject,
        portal_url=portal_url,
    )
    plain_out = f"Заявка №TKT-{ticket.number}: {ticket.subject}\n{'-' * 40}\n\n{body_plain}"
    return html_out, plain_out


def render_system_email(
    *,
    ticket: HelpdeskTicket,
    body_html: str,
    body_text: str,
    portal_url: str | None = None,
) -> tuple[str, str]:
    """Обёртка для системного письма (назначение ответственного): шапка + контент
    + футер. Без reply-разделителя и истории."""
    html_out = _wrap(
        f'<div style="padding:0 0 8px;">{_absolutize_img_src(body_html)}</div>',
        ticket_number=ticket.number,
        subject=ticket.subject,
        portal_url=portal_url,
    )
    plain_out = f"Заявка №TKT-{ticket.number}: {ticket.subject}\n{'-' * 40}\n\n{body_text}"
    return html_out, plain_out
