"""Единый HTML-шаблон исходящих helpdesk-писем (ответ агента + системные).

Минималистичный дизайн: компактная шапка (единый заголовок «#номер — тема»),
таймлайн переписки с горизонтальными разделителями между сообщениями (без левых
вертикальных полос/карточек — различение участников цветом имени и подписью
роли), заметный reply-разделитель, приглушённые автоматические подписи
отправителей (эвристика), компактный блок вложений.

Жёстко зафиксированный шрифт — Times New Roman 14px (по запросу владельца):
единый шрифт и размер во всём письме, иерархия — через ``font-weight``/``color``,
а не через размеры. Референс в проекте — ``news/email_share.py`` (табличная
вёрстка 600px, inline-стили — почтовые клиенты игнорируют CSS-классы).

Все user-facing данные экранируются через ``html.escape`` (паттерн meetings/news).

Шаблон применяется в:
* ``_try_enqueue_outbound`` (ответ агента + история) → ``render_reply_email``;
* ``build_assigned_email_bodies`` (назначение ответственного) → ``render_system_email``.

Reply-маркеры (``build_reply_marker_*``) переносятся сюда из ``email_quote``:
``REPLY_MARKER_TOKEN`` — это видимый текст инструкции «Ответьте выше этой линии»,
он же служит якорем для отсечения цитаты (``strip_quoted_html`` ловит фразу с
допуском обёртывающих тегов, см. regex ``_OWN_MARKER_HTML_RE``). Видимый текст
выбран намеренно: скрытые якоря ненадёжно переживают ответ в Outlook.

Чистые функции — тестируются без БД.
"""

from __future__ import annotations

import html
import re
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.helpdesk import HelpdeskMessage, HelpdeskTicket

# ── Палитра (минимализм уровня GitHub/Linear) ───────────────────────────────
#
# Спокойный brand-blue вместо насыщенной шапки-полосы. Письмо читается как
# уведомление, а не как веб-страница: максимум типографики, минимум рамок/фона.

_ACCENT = "#0969da"  # brand: имя специалиста, ссылки
_TEXT = "#1f2328"  # основной текст (ответ агента, тема)
_TEXT_TIMELINE = "#24292f"  # тело сообщений таймлайна (чуть мягче основного)
_NAME_REQUESTER = "#57606a"  # secondary grey: имя заявителя
_ROLE_LABEL = "#8c959f"  # приглушённая подпись роли («Специалист поддержки»)
_META = "#8c959f"  # даты, футер
_BORDER = "#ebeef2"  # тонкий разделитель (футер)
_BORDER_SEP = "#d8dee4"  # горизонтальный разделитель между сообщениями таймлайна
# Жёстко зафиксированный шрифт письма — Times New Roman 14px (по запросу владельца):
# корпоративный «документальный» стиль, единый шрифт и размер во всём письме.
# Иерархия — через font-weight и цвет, а не через размеры.
_FONT = "'Times New Roman', Times, serif"
_FONT_SIZE = "14px"
_WIDTH = 600

# ``REPLY_MARKER_TOKEN`` и ``build_reply_marker_*`` — единый источник истины в
# ``email_quote`` (там же regex детекции при ответе заявителя). Шаблон только
# использует их. Импорт после объявления констант-палитры (noqa E402). Эти
# функции реэкспортируются (``__all__`` ниже) — call-сайты (включая тесты)
# импортируют их отсюда, а не напрямую из ``email_quote``.
from app.services.helpdesk.email_quote import (  # noqa: E402
    build_reply_marker_html,
    build_reply_marker_plain,
)

__all__ = [
    "build_reply_marker_html",
    "build_reply_marker_plain",
    "render_history_block",
    "render_reply_email",
    "render_system_email",
]

# ── Шапка / футер ────────────────────────────────────────────────────────────


def _esc(value: str | None) -> str:
    """Экранирование пользовательских данных (паттерн news ``_esc``)."""
    return html.escape(value or "", quote=True)


def _header_html(ticket_number: int, subject: str) -> str:
    """Компактная шапка письма: единый заголовок «#номер — тема».

    Один шрифт (Times New Roman 14px), иерархия — через ``font-weight``/``color``,
    не через размеры. Без строки исполнителя (убрана по запросу — роль видна в
    таймлайне по подписи «Исполнитель»/«Специалист поддержки»).
    """
    subject_esc = _esc(subject)
    return (
        # Заголовок: «#номер — тема» одной строкой, единый шрифт/размер, bold.
        f'<div style="font-family:{_FONT};color:{_TEXT};font-size:{_FONT_SIZE};'
        f'font-weight:600;line-height:1.4;">'
        f"#{ticket_number} — {subject_esc}"
        "</div>"
    )

def _footer_html(portal_url: str | None) -> str:
    """Футер: призыв ответить на письмо (жирный, по центру) + ссылка на портал."""
    if portal_url:
        link = _esc(portal_url)
        portal_line = (
            '<div style="margin-top:8px;">'
            f'<a href="{link}" style="color:{_ACCENT};'
            'text-decoration:none;">Открыть заявку в портале</a>'
            "</div>"
        )
    else:
        portal_line = ""
    footer_style = (
        f"margin-top:32px;padding-top:20px;border-top:1px solid {_BORDER};"
        f"font-family:{_FONT};font-size:{_FONT_SIZE};text-align:center;"
    )
    return f"""\
<div style="{footer_style}">
  <div style="color:{_TEXT};font-weight:600;">
    Вы можете оставить комментарии по заявке ответив на это письмо
  </div>
  {portal_line}
</div>"""


def _wrap(
    content: str,
    *,
    ticket_number: int,
    subject: str,
    portal_url: str | None,
) -> str:
    """Обёртка: внешний контейнер 600px + шапка + контент + футер.

    Базовый шрифт (Times New Roman 14px) задаётся здесь на корневом ``<div>`` и
    наследуется всем письмом; дочерние блоки переопределяют только ``font-weight``/
    ``color`` (без отдельных ``font-size``)."""
    header = _header_html(ticket_number, subject)
    return (
        f'<div style="font-family:{_FONT};color:{_TEXT};font-size:{_FONT_SIZE};'
        f'line-height:1.55;">'
        f'<table role="presentation" width="{_WIDTH}" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;max-width:{_WIDTH}px;margin:0 auto;">'
        f'<tr><td style="padding:24px;">'
        f"{header}"
        f'<div style="margin-top:20px;">{content}{_footer_html(portal_url)}</div>'
        "</td></tr>"
        "</table>"
        "</div>"
    )


# ── Блок таймлайна ───────────────────────────────────────────────────────────


def _role_subtitle(*, is_outbound: bool, is_assignee: bool) -> str:
    """Приглушённая подпись роли рядом с именем сотрудника (без бейджей).

    * outbound (специалист) + автор = назначенный исполнитель → «Исполнитель».
    * outbound (специалист), не исполнитель → «Специалист поддержки».
    * inbound (заявитель) → без подписи (роль и так понятна из контекста).

    Возвращает inline-HTML-фрагмент (с ведущим разделителем) или пустую строку.
    """
    if not is_outbound:
        return ""
    label = "Исполнитель" if is_assignee else "Специалист поддержки"
    return (
        f'<span style="color:{_ROLE_LABEL};font-weight:400;'
        f'padding-left:6px;">{_esc(label)}</span>'
    )


def _timeline_block(
    *,
    who: str,
    when: str,
    body: str,
    attachments_html: str,
    is_outbound: bool,
    body_color: str,
    role_subtitle: str = "",
    prepend_separator: bool = False,
) -> str:
    """Один блок таймлайна: имя(роль) + дата + тело.

    Различение участников — только цветом имени и подписью роли (без левых
    вертикальных полос/рамок — по запросу):
    * inbound (от заявителя) — имя ``_NAME_REQUESTER`` (secondary grey).
    * outbound (от специалиста) — имя ``_ACCENT`` (brand) + приглушённая подпись
      «Специалист поддержки»/«Исполнитель».

    ``prepend_separator=True`` — вставляет горизонтальную линию (``<hr>``) на всю
    ширину письма перед блоком. Используется для разделения сообщений в истории.
    ``False`` — для блока ответа агента (идёт сразу после шапки, разделитель не нужен).

    Воздух ВНУТРИ блока (имя → дата → тело) увеличен; расстояние МЕЖДУ
    сообщениями диктуется разделителем (компактность длинных переписок).
    """
    name_color = _ACCENT if is_outbound else _NAME_REQUESTER
    separator = (
        f'<hr style="border:none;border-top:1px solid {_BORDER_SEP};'
        f'margin:18px 0 0;">'
        if prepend_separator
        else ""
    )
    return (
        separator
        + f'<div style="padding-top:16px;padding-bottom:4px;margin-top:16px;">'
        # Имя автора: semibold, accent/grey + приглушённая подпись роли.
        f'<div style="font-weight:600;color:{name_color};">'
        f"{who}{role_subtitle}</div>"
        # Дата — приглушённее имени (дополнительный воздух сверху).
        f'<div style="color:{_META};margin-top:5px;">{when}</div>'
        # Тело — с заметным воздухом после даты.
        f'<div style="color:{body_color};line-height:1.6;'
        f'margin-top:12px;">{body}</div>'
        # Вложения — компактный блок.
        f"{attachments_html}"
        "</div>"
    )


def render_history_block(
    msg: HelpdeskMessage,
    *,
    assignee_user_id: uuid.UUID | None = None,
) -> str:
    """Один блок истории как элемент таймлайна (минималистичный).

    Без карточек/бейджей/alternating-фона/вертикальных полос. Только:
    * горизонтальный разделитель (``<hr>``) на всю ширину письма перед блоком;
    * имя автора (accent для специалиста / grey для заявителя) + приглушённая
      подпись роли для специалиста;
    * дата (мельче и приглушённее имени);
    * тело;
    * компактный блок вложений.

    ``assignee_user_id`` — для подписи «Исполнитель» (если автор сообщения =
    назначенный специалист тикета). Сравнение UUID, без доп. запросов к БД.
    """
    is_outbound = msg.direction == "outbound"
    author_user_id = getattr(msg, "author_user_id", None)
    is_assignee = (
        is_outbound
        and author_user_id is not None
        and assignee_user_id is not None
        and author_user_id == assignee_user_id
    )
    who = _esc(msg.author_name or msg.author_email or "?")
    when = _esc(_format_date(msg.created_at))
    body = _message_body_html(msg)
    attachments_html = _attachments_html(msg)
    role_subtitle = _role_subtitle(is_outbound=is_outbound, is_assignee=is_assignee)
    return _timeline_block(
        who=who,
        when=when,
        body=body,
        attachments_html=attachments_html,
        is_outbound=is_outbound,
        body_color=_TEXT_TIMELINE,
        role_subtitle=role_subtitle,
        prepend_separator=True,
    )


# ── Тело сообщения + отсечение подписи отправителя ─────────────────────────


# Маркеры начала email-подписи. Берём самые типичные (RFC 3676 ``-- ``, формулы
# вежливости ru/en). Применяются только в последней трети тела — чтобы не срезать
# легитимное «спасибо/С уважением» в середине ответа.
_SIG_PLAIN_MARKERS = (
    r"-{2,}[ \t]*(?:\r?\n|$)",  # RFC 3676 sig separator: "-- " / "---"
    r"С\s*уважением[,.]?",
    r"С\s*наилучшими\s+пожеланиями[,.]?",
    r"Best\s*regards[,.]?",
    r"Kind\s*regards[,.]?",
    r"Yours\s+(?:truly|sincerely|faithfully)[,.]?",
    r"Respectfully[,.]?",
    r"(?<!\w)Regards[,.]?",
)
# Plain: маркер в начале строки.
_SIG_PLAIN_RE = re.compile(
    r"(?:^[ \t]*(?:" + "|".join(_SIG_PLAIN_MARKERS) + r"))",
    re.IGNORECASE | re.MULTILINE,
)

# HTML-маркеры — отдельный список (с допуском inline-тегов между/вокруг слов).
# nh3 сохраняет <b>/<i>/<span>/<br>/<div>/<p>/<font>/<u>/<a>; формулы вежливости
# почтовики часто оборачивают в теги («<b>С уважением</b>»). ``[T]`` — аналог
# ``\s*`` с допуском inline-тегов и ``&nbsp;``. Сепаратор ``--`` здесь не нужен:
# он ловится отдельным ``<hr>``-слоем ниже (а ``-- `` в HTML обычно без тегов).
_T = r"(?:</?(?:b|strong|i|em|span|font|u|a|br|p|div)\b[^>]*>|[ \t\r\n]|&nbsp;)*"
_SIG_HTML_MARKERS = (
    rf"С{_T}уважением{_T}[,.]?",
    rf"С{_T}наилучшими{_T}пожеланиями{_T}[,.]?",
    rf"Best{_T}regards{_T}[,.]?",
    rf"Kind{_T}regards{_T}[,.]?",
    rf"Yours{_T}(?:truly|sincerely|faithfully){_T}[,.]?",
    rf"Respectfully{_T}[,.]?",
)
_SIG_HTML_RE = re.compile(
    r"(?:" + "|".join(_SIG_HTML_MARKERS) + r")",
    re.IGNORECASE,
)
# Минимальная длина тела, чтобы вообще искать подпись (короткие реплики — без неё).
_SIG_MIN_LEN = 40
# Подпись ищем начиная с ~1/3 тела (маркер должен стоять в заметной второй части,
# но короткие тела с подписью тоже ловятся). Защищает легитимное «спасибо/
# С уважением» в самом начале/середине ответа от ложного отсечения.
_SIG_MIN_FRACTION = 0.33

_SIGNATURE_HIDDEN_HTML = (
    f'<div style="margin-top:8px;color:{_META};'
    f'font-style:italic;">↧ Подпись отправителя скрыта</div>'
)


def _split_signature_plain(text: str) -> tuple[str, bool]:
    """Отсечь подпись в plain-тексте. Возвращает ``(тело, была_ли_подпись)``.

    Берём **последнее** совпадение маркера по всему телу и отсекаем от него до
    конца, но только если маркер стоит во второй половине текста. Подпись —
    терминальный блок, поэтому последнее совпадение надёжнее первого.
    """
    if not text or len(text) < _SIG_MIN_LEN:
        return text, False
    threshold = len(text) * _SIG_MIN_FRACTION
    last: re.Match[str] | None = None
    for m in _SIG_PLAIN_RE.finditer(text):
        if m.start() >= threshold:
            last = m  # берём последнее совпадение во второй половине
    if last is None:
        return text, False
    body = text[: last.start()].rstrip()
    return body, True


def _split_signature_html(html_body: str) -> tuple[str, bool]:
    """Отсечь подпись в HTML. Best-effort: ``<hr>``-разделитель или текстовый
    маркер (``С уважением``/``Best regards``) с допуском inline-тегов.

    HTML-подпись отделить от тела сложнее (теги между словами), поэтому два слоя,
    оба берут **последнее** совпадение во второй половине тела:
      1. ``<hr>`` — классический разделитель подписи (Outlook/Gmail). Режем от
         последнего ``<hr>`` до конца.
      2. Текстовый маркер — формулы вежливости с допуском inline-тегов
         (nh3 сохраняет ``<b>``/``<i>``/``<span>``/``<br>``).
    Возвращает ``(очищенный_html, была_ли_подпись)``. Без совпадения — как есть.
    """
    if not html_body or len(html_body) < _SIG_MIN_LEN:
        return html_body, False
    threshold = len(html_body) * _SIG_MIN_FRACTION
    # 1. Последний <hr> во второй половине.
    hr_last: re.Match[str] | None = None
    for hr in re.finditer(r"<hr\b[^>]*>\s*", html_body, re.IGNORECASE):
        if hr.start() >= threshold:
            hr_last = hr
    if hr_last is not None:
        body = html_body[: hr_last.start()].rstrip()
        return body, True
    # 2. Последний текстовый маркер во второй половине.
    sig_last: re.Match[str] | None = None
    for sig in _SIG_HTML_RE.finditer(html_body):
        if sig.start() >= threshold:
            sig_last = sig
    if sig_last is not None:
        body = html_body[: sig_last.start()].rstrip()
        return body, True
    return html_body, False


def _message_body_html(msg: HelpdeskMessage) -> str:
    """Тело сообщения: sanitized ``body_html`` или ``<div>`` из plain (не ``<pre>``,
    чтобы не было моноширинного «код»-вида). В обоих случаях отсекается
    автоматическая подпись отправителя (эвристика) — в письме подпись приглушается
    блоком «Подпись скрыта», в БД и веб-версии тикета остаётся полностью."""
    if msg.body_html:
        body, had_sig = _split_signature_html(msg.body_html)
        out = body
    else:
        text = (msg.body_text or "").strip()
        if not text:
            return ""
        clean, had_sig = _split_signature_plain(text)
        out = f'<div style="white-space:pre-wrap;">{_esc(clean)}</div>'
    if had_sig:
        out += _SIGNATURE_HIDDEN_HTML
    return out


# ── Вложения ────────────────────────────────────────────────────────────────


def _format_size(size_bytes: object) -> str:
    """Компактное человекочитаемое представление размера файла."""
    try:
        n = int(size_bytes)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{n} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return ""


def _attachments_html(msg: HelpdeskMessage) -> str:
    """Блок вложений сообщения. Делегирует в ``_attachments_list_html``."""
    return _attachments_list_html(getattr(msg, "attachments", None) or [])


def _attachments_list_html(atts: list | None) -> str:
    """Компактный блок вложений (абсолютные URL). Пусто если нет вложений.

    Ссылки абсолютные (``{portal_base_url}/api/v1/helpdesk/attachments/{id}``) —
    почтовый клиент не резолвит относительные пути. Компактно: заголовок «📎
    Вложения» + список строк «имя (размер)», без рамок и больших отступов."""
    if not atts:
        return ""
    base = _portal_base_url()
    rows: list[str] = []
    for a in atts:
        name = _esc(getattr(a, "original_name", None) or "файл")
        size = _format_size(getattr(a, "size_bytes", None))
        url = f"{base}/api/v1/helpdesk/attachments/{getattr(a, 'id', '')}"
        size_html = f" <span style=\"color:{_META};\">({_esc(size)})</span>" if size else ""
        rows.append(
            f'<div style="margin-top:3px;">'
            f'<a href="{url}" style="color:{_ACCENT};'
            f'text-decoration:none;">{name}</a>{size_html}'
            "</div>"
        )
    return (
        f'<div style="margin-top:12px;color:{_NAME_REQUESTER};'
        f'font-weight:600;">📎 Вложения</div>'
        + "".join(rows)
    )


# ── Дата / URL / img-src ────────────────────────────────────────────────────


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
    assignee_user_id: uuid.UUID | None = None,
    message_author_user_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Обёртка для письма-ответа агента: шапка + ответ + разделитель + история + футер.

    Возвращает ``(html, plain)``. ``history_*`` пустые → разделитель + заголовок
    истории не добавляются (первый ответ на заявку — истории ещё нет).

    ``assignee_user_id`` + ``message_author_user_id`` — для подписи «Исполнитель»
    в блоке ответа агента (если автор = назначенный специалист). Без доп. запросов.
    """
    has_history = bool(history_html.strip())
    marker_html = build_reply_marker_html(ticket.number)
    marker_plain = build_reply_marker_plain(ticket.number)
    reply_date = _format_date(message_created_at) if message_created_at is not None else ""
    # Переписать относительные img-src на абсолютные (веб-вид → почта): без этого
    # картинки из body агента и истории (src="/api/...") не грузятся в письме.
    agent_body_html = _absolutize_img_src(agent_body_html)
    history_html = _absolutize_img_src(history_html)

    # Блок ответа агента — таймлайн outbound-стиля (accent-имя + приглушённая
    # подпись «Исполнитель»/«Специалист поддержки»), единый визуальный язык с
    # историей. Тело — основным цветом (не secondary), чтобы ответ визуально
    # лидировал. Подпись «Исполнитель» если автор ответа = назначенный специалист.
    is_assignee_reply = (
        assignee_user_id is not None
        and message_author_user_id is not None
        and assignee_user_id == message_author_user_id
    )
    role_subtitle = _role_subtitle(is_outbound=True, is_assignee=is_assignee_reply)
    body_html = _timeline_block(
        who=_esc(message_author),
        when=_esc(reply_date),
        body=agent_body_html,
        attachments_html=_attachments_list_html(message_attachments),
        is_outbound=True,
        body_color=_TEXT,
        role_subtitle=role_subtitle,
        prepend_separator=False,
    )
    body_plain = agent_body_text

    if has_history:
        body_html += marker_html
        body_html += (
            f'<div style="margin-top:28px;">'
            # Спокойный заголовок обычным регистром (не uppercase), inherit 14px.
            f'<div style="color:{_META};font-weight:600;'
            f'margin-bottom:2px;">Предыдущие сообщения</div>'
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
