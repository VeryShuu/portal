"""Отсечение цитируемых писем во входящих helpdesk-ответах.

Проблема: когда заявитель отвечает на письмо тикета через почтовый клиент
(Outlook/Thunderbird/Gmail), клиент добавляет блок цитаты предыдущего сообщения
(``From:``/``Sent:``/``To:``/``Subject:`` + текст, либо ``On … wrote:`` и
``>``-префиксы). Без отсечения весь этот блок попадает в ``helpdesk_messages.body_text``
и в ленте тикета ответ выглядит странно (вместе с предыдущим письмом).

Подход — промышленный стандарт (Zammad/FreeScout/Help Scout), два слоя:

1. **Маркер-разделитель** в исходящих письмах (``build_reply_marker_*``) —
   контролируем оба конца, режем строго по своему уникальному токену
   (``REPLY_MARKER_TOKEN``). Самый надёжный слой.
2. **Эвристический fallback** для писем без маркера: первый тикет (клиент пишет
   сам, без ответа на наше письмо), либо почтовик клиента съел маркер. Срабатывает
   по стандартным паттернам цитирования (``_QUOTE_PATTERNS``).

Чистые функции + module-level compiled regex — тестируется без БД (образец —
``app.services.helpdesk.threading``).
"""

from __future__ import annotations

import re

# Уникальный стабильный токен-разделитель. Не зависит от номера тикета, чтобы
# при изменении нумерации/импорте архива обрезка продолжала работать.
# Появляется в обоих представлениях (plain + html) исходящего письма.
REPLY_MARKER_TOKEN = "portal-helpdesk-reply-marker"

# Тривиальная деривация plain-текста из HTML: удаление тегов. Не заменяет
# полноценный HTML→text (html2text и т.п.), но достаточна для body_text-копии
# письма/сообщения, где html — уже sanitized. Применяется в ingress при
# локализации картинок (обновлённый html) и деривации plain из sanitized html.
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_plain(html: str) -> str:
    """Снять HTML-теги, схлопнув пробелы. Пустой/None → пустая строка."""
    return _TAG_RE.sub(" ", html or "").strip()


# ── Эвристика quoted-reply (fallback, когда маркера нет) ─────────────────────
# Каждый паттерн привязан к началу строки (``re.M``) — чтобы случайно не обрезать
# легитимный текст, где встретилось «От:»/«From:»/«-----». Паттерны описывают
# заголовок блока цитаты, ставимый почтовыми клиентами.
_QUOTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Outlook: «-----Original Message-----» / «----- Исходное сообщение -----»
    # / «----- Исходного сообщения -----». Локализации ru/en.
    re.compile(
        r"^\s*-{2,}\s*(?:Original\s+Message|Исходн(?:ого|ое)\s+сообщени[ея]"
        r"|Оригинал(?:ьного|ьное)\s+сообщени[ея])\s*-{2,}",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Gmail (en): «On <date>, <author> wrote:» — многострочный заголовок
    re.compile(r"^On\s.+\bwrote:\s*$", re.IGNORECASE | re.MULTILINE),
    # Gmail (ru): «<date> <author> написал(а):» / «написал:» / «написала:»
    re.compile(r"^.+\bнаписа[л](?:\(а\)|а)?:\s*$", re.IGNORECASE | re.MULTILINE),
    # Outlook (en/ru): блок заголовков «From:\nSent:\nTo:\nSubject:» /
    # «От:\nОтправлено:\nКому:\nТема:». Берём 2 первые строки как сигнатуру блока.
    re.compile(
        r"^\s*(?:From|От):\s.+\n\s*(?:Sent|Отправлено):",
        re.IGNORECASE | re.MULTILINE,
    ),
)

# HTML quote-контейнеры, проставляемые почтовыми клиентами. Универсальный
# ``<blockquote>`` НЕ трогаем — это легитимное форматирование ответа.
# Внимание: WordSection1/2 (Outlook) сюда НЕ входят — это контейнер ВСЕГО
# письма (оборачивает и ответ, и цитату), поэтому отсечение от него режет
# от позиции 0 и не даёт эффекта. Цитата Outlook ловится по нашему маркеру
# (текст ``REPLY_MARKER_TOKEN`` survives sanitization) или по ``From:/Sent:``
# в деривированной plain-части.
_HTML_QUOTE_RE = re.compile(
    r"<(blockquote|div|span)\b[^>]*\bclass\s*=\s*"
    r'"[^"]*\b(?:gmail_quote|moz-cite-prefix|gmail_extra|quote)\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

# HTML quote-header (Outlook): ``<b><span>From:</span></b> ... <br><b>Sent:</b>``
# — однозначный признак начала блока цитаты в HTML. nh3 сохраняет ``<b>`` и
# ``<span>``. Локализации: ``От:/Отправлено:`` (ru). Берём с предшествующим
# открывающим ``<div>``/``<p>``, чтобы отрезать весь блок целиком.
_HTML_OUTLOOK_HEADER_RE = re.compile(
    r"(?:<div\b[^>]*>|<p\b[^>]*>)?\s*<b\b[^>]*>\s*(?:<span\b[^>]*>)?"
    r"(?:From|От)\s*:\s*(?:</span>)?\s*</b>",
    re.IGNORECASE,
)

# Наш собственный HTML-маркер. Изначально ставим ``<div class="portal-reply-marker">
# {TOKEN}</div>``, но почтовые клиенты (Outlook) при ответе разносят структуру:
# класс теряется, а текст-маркер оказывается в ``<div><p class="MsoNormal">
# {TOKEN}</p></div>``. Поэтому ищем не класс, а **открывающий тег, предшествующий
# вхождению текста-маркера**. Берём вместе с предшествующим ``<hr>``, чтобы не
# оставлять «висячий» разделитель.
_OWN_MARKER_HTML_RE = re.compile(
    r"(?:<hr\s*/?>)?\s*<\w+\b[^>]*>\s*(?:<\w+\b[^>]*>\s*)?" + re.escape(REPLY_MARKER_TOKEN),
    re.IGNORECASE,
)


def build_reply_marker_plain(ticket_number: int) -> str:
    """Маркер-разделитель для plain-text части исходящего письма (точка отсечения
    цитаты при ответе заявителя).

    Токен ``REPLY_MARKER_TOKEN`` — на отдельной строке, чтобы ``strip_quoted_reply``
    забирал блок целиком без хвостов.
    """
    return (
        f"\n\n--- {REPLY_MARKER_TOKEN} ---\n"
        "✂ Ответьте выше этой строки\n"
        f"[#TKT-{ticket_number}]\n"
        "---\n"
    )


def build_reply_marker_html(ticket_number: int) -> str:
    """Маркер-разделитель для HTML-части: пунктирная плашка с инструкцией.

    ``REPLY_MARKER_TOKEN`` спрятан — визуально невидим (``font-size:0;
    color:#fafafa`` сливается с фоном плашки ``#fafafa``), но физически остаётся
    в DOM сразу после открывающего ``<div>``. Это требование regex
    ``_OWN_MARKER_HTML_RE`` (ищет тег перед текстом-маркером, т.к. почтовики
    теряют CSS-класс при ответе). Скрытие через ``display:none`` рискованнее —
    некоторые почтовики при цитировании выкидывают ``display:none``-узлы; здесь
    токен физически присутствует в тексте письма, просто невидим глазом.
    """
    return (
        f'<div style="margin:24px 0 0;padding:10px 14px;border:2px dashed #bbb;'
        "border-radius:6px;background:#fafafa;"
        "font-family:sans-serif;"
        'color:#888;font-size:12px;line-height:1.5;">'
        # Токен: невидим (font-size:0, цвет = фон плашки), но в DOM.
        f'<div style="font-size:0;line-height:0;color:#fafafa;'
        f'max-height:0;overflow:hidden;">{REPLY_MARKER_TOKEN}</div>'
        "✂ Ответьте выше этой строки — история ниже будет скрыта"
        f"<br>[#TKT-{ticket_number}]"
        "</div>"
    )


def strip_quoted_reply(text: str) -> str:
    """Обрезать цитату предыдущего письма из plain-text тела.

    Слои (по надёжности):
      1. Наш маркер ``REPLY_MARKER_TOKEN`` — режем строго по нему.
      2. Эвристика ``_QUOTE_PATTERNS`` — режем по первому совпадению.

    Если ничего не найдено — возвращает ``text`` без изменений.
    """
    if not text:
        return text

    # 1. Наш маркер — самый надёжный слой. Токен стоит в начале строки блока
    # (``--- portal-helpdesk-reply-marker ---``), поэтому режем от начала
    # этой строки, захватывая предшествующие пустые строки-разделитель.
    idx = text.find(REPLY_MARKER_TOKEN)
    if idx >= 0:
        line_start = text.rfind("\n", 0, idx)
        cut = line_start + 1 if line_start >= 0 else 0
        kept = text[:cut].rstrip()
        return kept or text  # пустой ответ выше маркера → вернуть как есть

    # 2. Эвристика: первое (самое раннее) совпадение паттерна цитаты.
    earliest = len(text)
    for pat in _QUOTE_PATTERNS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    if earliest < len(text):
        kept = text[:earliest].rstrip()
        return kept or text
    return text


def strip_quoted_html(html: str) -> str:
    """Обрезать цитату предыдущего письма из HTML-тела.

    Многослойная обрезка (каждый слой работает с результатом предыдущего):
      1. Наш маркер ``REPLY_MARKER_TOKEN`` — отрезает reply-маркер + историю
         под ним. Почтовые клиенты (Outlook) разносят ``<div class="portal-
         reply-marker">`` в ``<div><p>{TOKEN}</p></div>`` (класс теряется),
         поэтому ищем открывающий тег, предшествующий тексту-маркеру.
      2. Outlook quote-header ``<b>From:</b>`` / ``<b>От:</b>`` — отрезает
         процитированный ответ агента над маркером.
      3. HTML quote-контейнеры почтовых клиентов (``gmail_quote`` и т.п.).

    Универсальный ``<blockquote>`` без классов не трогает — это легитимное
    форматирование. Точная обрезка сбалансированных тегов не реализуется: на
    входе всегда sanitized HTML (``nh3``), и quote-блок — почти всегда
    терминальный, поэтому отсечение от его начала до конца строки безопасно.
    """
    if not html:
        return html

    kept = html

    # 1. Наш маркер (отрезает маркер + историю).
    m = _OWN_MARKER_HTML_RE.search(kept)
    if m:
        kept = kept[: m.start()].rstrip()

    # 2. Outlook quote-header (отрезает процитированный ответ агента).
    m = _HTML_OUTLOOK_HEADER_RE.search(kept)
    if m:
        kept = kept[: m.start()].rstrip()

    # 3. Известные quote-контейнеры (gmail_quote/moz-cite-prefix/quote).
    m = _HTML_QUOTE_RE.search(kept)
    if m:
        kept = kept[: m.start()].rstrip()

    return kept or html
