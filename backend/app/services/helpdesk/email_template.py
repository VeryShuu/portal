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
_ROLE_LABEL = "#8c959f"  # приглушённая подпись «Сообщение от»
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
    "render_new_ticket_agent_email",
    "render_reply_email",
    "render_requester_reply_agent_email",
    "render_system_email",
]

# ── Шапка / футер ────────────────────────────────────────────────────────────


def _esc(value: str | None) -> str:
    """Экранирование пользовательских данных (паттерн news ``_esc``)."""
    return html.escape(value or "", quote=True)


def _header_html(ticket_number: int, subject: str) -> str:
    """Компактная шапка письма: единый заголовок «#номер — тема» по центру.

    Один шрифт (Times New Roman 14px), иерархия — через ``font-weight``/``color``,
    не через размеры. Без строки исполнителя (убрана по запросу — автор виден в
    таймлайне по подписи «Сообщение от — {ФИО}»).
    """
    subject_esc = _esc(subject)
    return (
        # Заголовок: «#номер — тема» одной строкой, единый шрифт/размер, bold, по центру.
        f'<div style="font-family:{_FONT};color:{_TEXT};font-size:{_FONT_SIZE};'
        f'font-weight:600;line-height:1.4;text-align:center;">'
        f"#{ticket_number} — {subject_esc}"
        "</div>"
    )


def _footer_html(portal_url: str | None) -> str:
    """Футер письма заявителю: призыв ответить на письмо (жирный, по центру) +
    ссылка на портал."""
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


def _agent_footer_html(portal_url: str | None) -> str:
    """Футер агентского письма-уведомления (о новой заявке): ссылка на портал +
    приглушённая подпись «автоматическое уведомление».

    Без призыва «ответьте на письмо»: агент работает через портал/инбокс, ответ
    на это письмо (через общий SMTP-from) создал бы путаницу в треде тикета
    (у этого письма нет threading-заголовков ``Message-ID``/``References`` —
    outbox ``kind=generic``, не ``helpdesk``)."""
    if portal_url:
        link = _esc(portal_url)
        portal_line = (
            f'<div style="margin-top:8px;">'
            f'<a href="{link}" style="color:{_ACCENT};'
            f'text-decoration:none;">Открыть заявку в портале</a>'
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
  <div style="color:{_META};">Это автоматическое уведомление техподдержки</div>
  {portal_line}
</div>"""


def _wrap(
    content: str,
    *,
    ticket_number: int,
    subject: str,
    portal_url: str | None,
    footer: str | None = None,
) -> str:
    """Обёртка: внешний контейнер + шапка + контент + футер.

    Базовый шрифт (Times New Roman 14px) задаётся здесь на корневом ``<div>`` и
    наследуется всем письмом; дочерние блоки переопределяют только ``font-weight``/
    ``color`` (без отдельных ``font-size``). Контент — на всю ширину письма
    (без 600px-ограничения, как в OTRS): таблица ``width:100%``.

    ``footer`` — кастомный футер (например, агентский ``_agent_footer_html``);
    ``None`` → дефолтный заявительский ``_footer_html``."""
    header = _header_html(ticket_number, subject)
    footer_html = footer if footer is not None else _footer_html(portal_url)
    return (
        f'<div style="font-family:{_FONT};color:{_TEXT};font-size:{_FONT_SIZE};'
        f'line-height:1.55;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;width:100%;">'
        f'<tr><td style="padding:24px;">'
        f"{header}"
        f'<div style="margin-top:20px;">{content}{footer_html}</div>'
        "</td></tr>"
        "</table>"
        "</div>"
    )


# ── Блок таймлайна ───────────────────────────────────────────────────────────


def _role_prefix() -> str:
    """Префикс перед именем автора сообщения: единое «Сообщение от — » для всех
    (и агента, и заявителя). Роль/направление больше не различаются — имя автора
    само по себе идентифицирует отправителя.

    Раньше было «Исполнитель — »/«Специалист поддержки — » для outbound и пусто
    для inbound (заявителя). По запросу унифицировано: «Сообщение от — {ФИО}».
    """
    label = "Сообщение от"
    return f'<span style="color:{_ROLE_LABEL};font-weight:400;">{_esc(label)} — </span>'


def _timeline_block(
    *,
    who: str,
    body: str,
    attachments_html: str,
    is_outbound: bool,
    body_color: str,
    role_prefix: str = "",
    prepend_separator: bool = False,
) -> str:
    """Один блок таймлайна: подпись (роль — имя) + тело.

    Различение участников — только цветом имени (без левых вертикальных полос/рамок
    — по запросу). Префикс «Сообщение от — » единый для всех:
    * inbound (от заявителя) — имя ``_NAME_REQUESTER`` (secondary grey) + префикс.
    * outbound (от специалиста) — имя ``_ACCENT`` (brand) + тот же префикс.

    Дата/время НЕ выводятся (по запросу — дата уже есть в письме: заголовок
    ``Date`` письма заявитель видит в почтовом клиенте, плюс тред emails несёт
    тайминги). ``prepend_separator=True`` — горизонтальная линия (``<hr>``) перед
    блоком (разделитель сообщений истории). ``False`` — для блока ответа агента
    (идёт сразу после шапки).
    """
    name_color = _ACCENT if is_outbound else _NAME_REQUESTER
    separator = (
        f'<hr style="border:none;border-top:1px solid {_BORDER_SEP};margin:18px 0 0;">'
        if prepend_separator
        else ""
    )
    return (
        separator + f'<div style="padding-top:16px;padding-bottom:4px;margin-top:16px;">'
        # Подпись: префикс роли (приглушённый) + имя (semibold, accent/grey).
        f'<div style="font-weight:600;color:{name_color};">'
        f"{role_prefix}{who}</div>"
        # Тело — с заметным воздухом после подписи.
        f'<div style="color:{body_color};line-height:1.6;'
        f'margin-top:10px;">{body}</div>'
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
    * подпись: префикс роли (для специалиста) + имя (accent для специалиста /
      grey для заявителя);
    * тело;
    * компактный блок вложений.

    Дата/время не выводятся (по запросу — дата есть в письме).

    ``assignee_user_id`` — сохранён в сигнатуре для совместимости вызовов, но
    больше не влияет на префикс (унифицированное «Сообщение от — » для всех).
    """
    is_outbound = msg.direction == "outbound"
    who = _esc(msg.author_name or msg.author_email or "?")
    body = _message_body_html(msg)
    attachments_html = _attachments_html(msg)
    role_prefix = _role_prefix()
    return _timeline_block(
        who=who,
        body=body,
        attachments_html=attachments_html,
        is_outbound=is_outbound,
        body_color=_TEXT_TIMELINE,
        role_prefix=role_prefix,
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
        size_html = f' <span style="color:{_META};">({_esc(size)})</span>' if size else ""
        rows.append(
            f'<div style="margin-top:3px;">'
            f'<a href="{url}" style="color:{_ACCENT};'
            f'text-decoration:none;">{name}</a>{size_html}'
            "</div>"
        )
    return (
        f'<div style="margin-top:12px;color:{_NAME_REQUESTER};'
        f'font-weight:600;">📎 Вложения</div>' + "".join(rows)
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
    message_attachments: list | None = None,
    assignee_user_id: uuid.UUID | None = None,
    message_author_user_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Обёртка для письма-ответа агента: шапка + ответ + история + футер.

    Возвращает ``(html, plain)``. ``history_*`` пустые → история не добавляется
    (первый ответ на заявку — истории ещё нет).

    Reply-маркер («Ответьте выше этой линии») НЕ ставится: отсечение цитат при
    ответе заявителя работает по заголовкам почтового клиента (Outlook
    ``From:/Sent:``, Gmail ``wrote:``) через ``strip_quoted_reply``/``strip_quoted_html``
    — как в OTRS. Это убирает служебный текст из письма.

    Дата/время ответа НЕ выводятся (по запросу — дата есть в письме).

    ``assignee_user_id`` + ``message_author_user_id`` — сохранены для совместимости,
    но префикс ответа унифицирован («Сообщение от — » для всех, без различения
    assignee/не-assignee).
    """
    has_history = bool(history_html.strip())
    # Переписать относительные img-src на абсолютные (веб-вид → почта): без этого
    # картинки из body агента и истории (src="/api/...") не грузятся в письме.
    agent_body_html = _absolutize_img_src(agent_body_html)
    history_html = _absolutize_img_src(history_html)

    # Блок ответа агента — таймлайн outbound-стиля: префикс «Сообщение от — » +
    # accent-имя, единый визуальный язык с историей.
    # Тело — основным цветом (не secondary), чтобы ответ визуально лидировал.
    # Дата/время не выводаются (по запросу — дата есть в письме).
    role_prefix = _role_prefix()
    body_html = _timeline_block(
        who=_esc(message_author),
        body=agent_body_html,
        attachments_html=_attachments_list_html(message_attachments),
        is_outbound=True,
        body_color=_TEXT,
        role_prefix=role_prefix,
        prepend_separator=False,
    )
    body_plain = agent_body_text

    if has_history:
        # История идёт сразу за ответом агента, без отдельного заголовка
        # («Предыдущие сообщения» убран по запросу). Блоки истории несут свои
        # разделители (<hr>) — визуально они и отделяют ответ от истории.
        body_html += history_html
        body_plain += "\n\n" + history_plain

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


def _requester_contacts(
    ticket: HelpdeskTicket, requester: object | None
) -> tuple[list[tuple[str, str]], str]:
    """Контакты заявителя для письма-уведомления агентам.

    Возвращает ``(html_rows, plain_block)``:
    * ``html_rows`` — список ``(label, value_html)`` для блока контактов;
    * ``plain_block`` — многострочное plain-представление тех же данных.

    Источник данных — модель ``User`` (как в карточке тикета,
    ``build_requester_profile``): ФИО/email/department/position — нативные
    колонки, ``internal_phone`` — ``user.phone``, ``mobile_phone`` —
    ``user.attributes["mobile"]``. Поля с пустым значением пропускаются.

    Для гостевой заявки без аккаунта (``requester is None``) берём что есть из
    тикета: имя/из ``requester_name`` и ``requester_email`` (всегда заполнено).
    """
    rows: list[tuple[str, str]] = []
    plain_lines: list[str] = []

    if requester is not None:
        full_name = (getattr(requester, "full_name", None) or "").strip()
        email_addr = (getattr(requester, "email", None) or "").strip()
        internal = (getattr(requester, "phone", None) or "").strip() or None
        attrs = getattr(requester, "attributes", None)
        mobile = None
        if isinstance(attrs, dict):
            mval = attrs.get("mobile")
            if isinstance(mval, str) and mval.strip():
                mobile = mval.strip()
    else:
        # Гость без аккаунта в портале — только снимок из тикета.
        full_name = (getattr(ticket, "requester_name", None) or "").strip()
        email_addr = (getattr(ticket, "requester_email", None) or "").strip()
        internal = None
        mobile = None

    if full_name:
        rows.append(("ФИО", _esc(full_name)))
        plain_lines.append(f"ФИО: {full_name}")
    if email_addr:
        rows.append(("Почта", _esc(email_addr)))
        plain_lines.append(f"Почта: {email_addr}")
    if mobile:
        rows.append(("Телефон", _esc(mobile)))
        plain_lines.append(f"Телефон: {mobile}")
    if internal:
        rows.append(("Внутренний номер", _esc(internal)))
        plain_lines.append(f"Внутренний номер: {internal}")

    plain_block = "\n".join(plain_lines) if plain_lines else "—"
    return rows, plain_block


def _contacts_block_html(rows: list[tuple[str, str]]) -> str:
    """Компактный блок контактов заявителя (label: value по строкам).

    Метка — приглушённым цветом (``_NAME_REQUESTER``), значение — основным.
    Без рамок/фона — минимализм единого helpdesk-шаблона."""
    if not rows:
        return ""
    items = "".join(
        f'<div style="margin-top:4px;">'
        f'<span style="color:{_NAME_REQUESTER};">{_esc(label)}:</span> '
        f'<span style="color:{_TEXT};">{value}</span>'
        f"</div>"
        for label, value in rows
    )
    return f'<div style="margin-top:16px;">{items}</div>'


def render_new_ticket_agent_email(
    *,
    ticket: HelpdeskTicket,
    first_message: HelpdeskMessage,
    requester: object | None = None,
    portal_url: str | None = None,
) -> tuple[str, str]:
    """Письмо-уведомление агентам поддержки о новой заявке.

    Аналог OTRS-уведомления «В службу технической поддержки поступила новая
    заявка», но в едином стиле портала (шапка «#номер — тема» + минимализм).
    Содержит: «Поступила новая заявка» → блок контактов заявителя (ФИО, Почта,
    Телефон, Внутренний номер — из модели ``User``, как в карточке тикета) →
    «Текст заявки:» (тело первого сообщения в блоке-цитате) → ссылка на портал.

    ``requester`` — модель ``User`` заявителя (или ``None`` для гостевой заявки
    без аккаунта в портале; тогда берём снимок имени/email из тикета).

    Письмо отправляется через outbox ``kind=generic`` (не входит в email-тред
    тикета — без threading-заголовков). Футер — ``_agent_footer_html`` (без
    призыва «ответьте на письмо»: агент работает через портал/инбокс).

    Все пользовательские данные (ФИО/email/телефон/тело) экранируются через
    ``html.escape``. Тело — sanitized ``body_html`` (при email-ingress уже
    прошёл nh3) или ``<div>`` из plain (для web-заявок без body_html).
    """
    base = _portal_base_url()
    contacts_rows, contacts_plain = _requester_contacts(ticket, requester)
    contacts_html = _contacts_block_html(contacts_rows)

    # Тело первого сообщения. email-входящие уже sanitized (nh3 в ingress);
    # web-заявки приходят с body_html=None → оборачиваем plain в <div pre-wrap>.
    body_html_msg = getattr(first_message, "body_html", None)
    if body_html_msg:
        body_html_msg = _absolutize_img_src(body_html_msg)
        body_block = (
            f'<div style="background:#f5f5f5;border-left:3px solid {_BORDER_SEP};'
            f'color:{_TEXT_TIMELINE};margin:10px 0 0;padding:10px;">'
            f"{body_html_msg}</div>"
        )
    else:
        clean = (getattr(first_message, "body_text", None) or "").strip()
        body_block = (
            f'<div style="background:#f5f5f5;border-left:3px solid {_BORDER_SEP};'
            f"color:{_TEXT_TIMELINE};margin:10px 0 0;padding:10px;"
            f'white-space:pre-wrap;">{_esc(clean)}</div>'
        )

    content = (
        f'<div style="padding:0 0 8px;">Поступила новая заявка.</div>'
        f"{contacts_html}"
        f'<div style="margin-top:16px;font-weight:600;">Текст заявки:</div>'
        f"{body_block}"
    )

    # Ссылка на тикет в портале — абсолютная (агент кликает из почтового клиента).
    link = portal_url or f"{base}/helpdesk/tickets/{ticket.id}"
    html_out = _wrap(
        content,
        ticket_number=ticket.number,
        subject=ticket.subject,
        portal_url=link,
        footer=_agent_footer_html(link),
    )

    plain_body = (getattr(first_message, "body_text", None) or "").strip()
    plain_out = (
        f"Заявка №TKT-{ticket.number}: {ticket.subject}\n"
        f"{'-' * 40}\n\n"
        f"Поступила новая заявка.\n\n"
        f"{contacts_plain}\n\n"
        f"Текст заявки:\n{plain_body}\n\n"
        f"{link}"
    )
    return html_out, plain_out


def render_requester_reply_agent_email(
    *,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    requester: object | None = None,
    portal_url: str | None = None,
    history_html: str = "",
    history_plain: str = "",
) -> tuple[str, str]:
    """Письмо-уведомление агенту о новом сообщении от заявителя.

    Симметрично ``render_new_ticket_agent_email``, но для события «ответ клиента
    по существующему тикету» (а не создание новой заявки). Единый стиль портала:
    шапка «#номер — тема» → «Новое сообщение по заявке.» → блок контактов
    заявителя (кто ответил) → подпись «Сообщение от — {ФИО/email заявителя}» →
    тело ответа → агентский футер со ссылкой на инбокс.

    Письмо несёт **историю переписки** после нового ответа заявителя —
    симметрично ``render_reply_email`` (ответ агента инициатору): агент видит в
    почте тот же диалог, что и инициатор. История собирается caller'ом через
    ``build_thread_history`` (``exclude_id=message.id``) теми же
    таймлайн-блоками (``render_history_block``) — единый визуальный язык с
    письмом инициатору. Параметры по умолчанию пустые → первый ответ заявителя
    (предыстории нет) рендерится без разделителя истории (обратная совместимость
    со всеми существующими call-сайтами/тестами).

    Письмо отправляется через outbox ``kind=generic`` (не входит в email-тред
    тикета с заявителем — без threading-заголовков), как и уведомление о новой
    заявке. Агент работает через портал/инбокс, а не отвечая на это письмо.

    ``message`` — сообщение-ответ заявителя (тело берётся отсюда, а не из
    ``first_message`` тикета). ``requester`` — модель ``User`` заявителя (или
    ``None`` для гостевой заявки → имя/email из снимка тикета). Все
    пользовательские данные экранируются через ``html.escape``; тело — sanitized
    ``body_html`` (при web-ответе прошёл nh3 в роутере, при ingress — в ingress)
    или ``<div>`` из plain (для сообщений без body_html).
    """
    base = _portal_base_url()
    contacts_rows, contacts_plain = _requester_contacts(ticket, requester)
    contacts_html = _contacts_block_html(contacts_rows)

    # Подпись автора ответа: предпочтительно ФИО из аккаунта, иначе снимок из
    # сообщения (``author_name``/``author_email``), иначе из тикета.
    if requester is not None:
        who = (getattr(requester, "full_name", None) or "").strip()
    else:
        who = (getattr(message, "author_name", None) or "").strip()
    if not who:
        who = (
            getattr(message, "author_email", None)
            or getattr(ticket, "requester_email", None)
            or "Заявитель"
        )

    # Тело ответа. email-ingress и web-роутер уже sanitized (nh3); web-сообщения
    # без body_html → оборачиваем plain в <div pre-wrap>.
    body_html_msg = getattr(message, "body_html", None)
    if body_html_msg:
        body_html_msg = _absolutize_img_src(body_html_msg)
        body_block = (
            f'<div style="background:#f5f5f5;border-left:3px solid {_BORDER_SEP};'
            f'color:{_TEXT_TIMELINE};margin:10px 0 0;padding:10px;">'
            f"{body_html_msg}</div>"
        )
    else:
        clean = (getattr(message, "body_text", None) or "").strip()
        body_block = (
            f'<div style="background:#f5f5f5;border-left:3px solid {_BORDER_SEP};'
            f"color:{_TEXT_TIMELINE};margin:10px 0 0;padding:10px;"
            f'white-space:pre-wrap;">{_esc(clean)}</div>'
        )

    # Подпись «Сообщение от — {ФИО/email}» единым паттерном таймлайна.
    reply_label = f'{_role_prefix()}<span style="color:{_NAME_REQUESTER};">{_esc(who)}</span>'

    # История переписки (симметрично ``render_reply_email``): агент видит весь
    # диалог, как и инициатор. Переписываем относительные img-src на абсолютные
    # (веб-вид → почта) тем же вызовом, что в ``render_reply_email`` — иначе
    # картинки истории (src="/api/...") не грузятся в почтовом клиенте.
    history_html_abs = _absolutize_img_src(history_html) if history_html else ""

    content = (
        f'<div style="padding:0 0 8px;">Новое сообщение по заявке.</div>'
        f"{contacts_html}"
        f'<div style="margin-top:16px;font-weight:600;">{reply_label}</div>'
        f"{body_block}"
        # История идёт сразу за новым ответом (без отдельного заголовка — блоки
        # несут свои <hr>-разделители), как в ``render_reply_email``.
        f"{history_html_abs}"
    )

    # Ссылка на тикет в портале — абсолютная (агент кликает из почтового клиента).
    link = portal_url or f"{base}/helpdesk/tickets/{ticket.id}"
    html_out = _wrap(
        content,
        ticket_number=ticket.number,
        subject=ticket.subject,
        portal_url=link,
        footer=_agent_footer_html(link),
    )

    plain_body = (getattr(message, "body_text", None) or "").strip()
    # История в plain дописывается после нового ответа, если она есть (симметрично
    # HTML-блоку выше и ``render_reply_email``).
    history_plain_block = f"\n\n{history_plain}" if history_plain else ""
    plain_out = (
        f"Заявка №TKT-{ticket.number}: {ticket.subject}\n"
        f"{'-' * 40}\n\n"
        f"Новое сообщение по заявке.\n\n"
        f"{contacts_plain}\n\n"
        f"Сообщение от — {who}:\n{plain_body}"
        f"{history_plain_block}\n\n"
        f"{link}"
    )
    return html_out, plain_out
