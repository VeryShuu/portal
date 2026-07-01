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
_HTML_QUOTE_RE = re.compile(
    r'<(blockquote|div|span)\b[^>]*\bclass\s*=\s*'
    r'"[^"]*\b(?:gmail_quote|moz-cite-prefix|gmail_extra|WordSection1|'
    r'WordSection2|quote)\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

# Наш собственный HTML-маркер: открывающий тег с классом ``portal-reply-marker``
# (может стоять сразу после тела без ведущего перевода). Берём вместе с любым
# предшествующим ``<hr>``/переводом, чтобы не оставлять «висячий» разделитель.
_OWN_MARKER_HTML_RE = re.compile(
    r"(?:<hr\s*/?>)?\s*<div\b[^>]*\bclass\s*=\s*"
    r'"[^"]*\bportal-reply-marker\b[^"]*"[^>]*>',
    re.IGNORECASE,
)


def build_reply_marker_plain(ticket_number: int) -> str:
    """Маркер-разделитель для plain-text части исходящего письма.

    Ставится в конец ``body_text`` при enqueue в outbox (НЕ в сохраняемое в БД
    сообщение — чтобы в ленте портала агент видел свой чистый ответ).

    Токен ``REPLY_MARKER_TOKEN`` — в первой строке блока, чтобы обрезка по нему
    забирала блок целиком без хвостов.
    """
    return (
        f"\n\n--- {REPLY_MARKER_TOKEN} ---\n"
        "Ответьте выше этой строки\n"
        f"[#TKT-{ticket_number}]\n"
        "---\n"
    )


def build_reply_marker_html(ticket_number: int) -> str:
    """Маркер-разделитель для HTML-части исходящего письма (см. plain-вариант).

    Открывающий ``<div>`` с классом ``portal-reply-marker`` — первым, чтобы
    ``strip_quoted_html`` резал от него (вместе с ведущим ``<hr>``).
    """
    return (
        f'<div class="portal-reply-marker">{REPLY_MARKER_TOKEN}</div>'
        "<hr><em>Ответьте выше этой строки</em><br>"
        f"[#TKT-{ticket_number}]"
        "<hr>"
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

    Работает по известным классам quote-контейнеров почтовых клиентов
    (``gmail_quote``, ``moz-cite-prefix`` и т.п.) и по нашему собственному
    ``portal-reply-marker``. Универсальный ``<blockquote>`` без классов не
    трогает — это легитимное форматирование. Если контейнер не найден —
    возвращает ``html`` без изменений (цитату из plain-части поймает
    ``strip_quoted_reply`` после деривации plain ← html).

    Точная обрезка сбалансированных тегов не реализуется: на входе всегда sanitized
    HTML (``nh3``), и quote-контейнер — почти всегда терминальный блок в конце
    письма, поэтому отсечение от его начала до конца строки безопасно.
    """
    if not html:
        return html

    # 1. Наш маркер — режем по открывающему тегу (+ предшествующий <hr>).
    m = _OWN_MARKER_HTML_RE.search(html)
    if m:
        kept = html[: m.start()].rstrip()
        return kept or html

    # 2. Эвристика: первый известный quote-контейнер.
    m = _HTML_QUOTE_RE.search(html)
    if m:
        kept = html[: m.start()].rstrip()
        return kept or html
    return html
