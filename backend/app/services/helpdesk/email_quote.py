"""Отсечение цитируемых писем во входящих helpdesk-ответах.

Проблема: когда заявитель отвечает на письмо тикета через почтовый клиент
(Outlook/Thunderbird/Gmail), клиент добавляет блок цитаты предыдущего сообщения
(``From:``/``Sent:``/``To:``/``Subject:`` + текст, либо ``On … wrote:`` и
``>``-префиксы). Без отсечения весь этот блок попадает в ``helpdesk_messages.body_text``
и в ленте тикета ответ выглядит странно (вместе с предыдущим письмом).

Подход — промышленный стандарт (Zammad/FreeScout/Help Scout), два слоя:

1. **Маркер-разделитель** в исходящих письмах (``build_reply_marker_*``) —
   контролируем оба конца, режем строго по видимому тексту-инструкции
   (``REPLY_MARKER_TOKEN`` = «Ответьте выше этой линии»). Видимый текст выбран
   намеренно: скрытые якоря (``font-size:0``/HTML-комментарии) ненадёжно
   переживают ответ в Outlook (Word-рендер их вырезает) → тихое разрушение
   отсечения; видимый текст — переживает всегда. Самый надёжный слой.
2. **Эвристический fallback** для писем без маркера: первый тикет (клиент пишет
   сам, без ответа на наше письмо), либо почтовик клиента съел маркер. Срабатывает
   по стандартным паттернам цитирования (``_QUOTE_PATTERNS``).

Чистые функции + module-level compiled regex — тестируется без БД (образец —
``app.services.helpdesk.threading``).
"""

from __future__ import annotations

import html as _html
import re

# Стабильный текст-якорь точки отсечения цитаты. Это видимая инструкция
# заявителю — обычный текст, который переживает round-trip при ответе во ВСЕХ
# почтовых клиентах, включая Outlook (Word-рендер вырезает HTML-комментарии и
# скрытые ``font-size:0`` узлы, поэтому скрытый машинный токен ненадёжён).
# ``strip_quoted_reply``/``strip_quoted_html`` режут строго по этой фразе:
# всё ниже неё в ответе заявителя — процитированная история, она отбрасывается.
# Не зависит от номера тикета (при импорте архива обрезка продолжает работать).
REPLY_MARKER_TOKEN = "Ответьте выше этой линии"

# Тривиальная деривация plain-текста из HTML: удаление тегов. Не заменяет
# полноценный HTML→text (html2text и т.п.), но достаточна для body_text-копии
# письма/сообщения, где html — уже sanitized. Применяется в ingress при
# локализации картинок (обновлённый html) и деривации plain из sanitized html.
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_plain(html: str) -> str:
    """Снять HTML-теги, схлопнув пробелы. Пустой/None → пустая строка."""
    return _TAG_RE.sub(" ", html or "").strip()


# Numeric HTML entities (``&#NNN;`` / ``&#xNNN;``). SOGo и некоторые веб-клиенты
# кодируют весь русский текст письма в numeric entities («писал» →
# «&#1087;&#1080;&#1089;&#1072;&#1083;»). ``strip_quoted_html``/``strip_quoted_reply``
# гоняются по **сырому** письму (до nh3-декодирования), поэтому regex с буквальным
# русским текстом не матчатся. Декодируем numeric entities точечно перед match.
# Именованные (``&lt;``/``&gt;``/``&amp;``/``&nbsp;``) НЕ трогаем — иначе ``&lt;``
# станет ``<`` и ``[^<>]*`` в regex споткнётся, а теги превратятся в текст.
_NUMERIC_ENTITY_RE = re.compile(r"&#(?:[0-9]+|x[0-9a-fA-F]+);")


def _decode_numeric_entities(text: str) -> str:
    """Декодировать только numeric HTML entities (``&#NNN;`` / ``&#xNNN;``).

    Именованные entities (``&lt;``, ``&gt;``, ``&amp;``, ``&nbsp;``) сохраняются
    как есть — они структурно значимы для regex (email в ``&lt; &gt;``, ``&nbsp;``
    после разделителя). Полный ``html.unescape`` сломал бы и теги (``<p>`` →
    ``&lt;p&gt;``), и классы ``[^<>]*``.
    """
    if not text:
        return text
    return _NUMERIC_ENTITY_RE.sub(lambda m: _html.unescape(m.group()), text)


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
    # SOGo / Mail.ru-веб (en): «<date>, <author> wrote:» — без ведущего «On»
    # (в отличие от Gmail). Корпоративный webmail mail.mage.ru (SOGo) формирует
    # именно такой заголовок при ответе.
    re.compile(r"^.+\bwrote:\s*$", re.IGNORECASE | re.MULTILINE),
    # Gmail (ru): «<date> <author> написал(а):» / «написал:» / «написала:»
    re.compile(r"^.+\bнаписа[л](?:\(а\)|а)?:\s*$", re.IGNORECASE | re.MULTILINE),
    # SOGo / Mail.ru-веб (ru): «<date>, <author> писал(а):» / «писал:» /
    # «писала:». Отличается от Gmail-ru отсутствием приставки «на-» —
    # корпоративный webmail mail.mage.ru (SOGo) использует краткую форму.
    re.compile(r"^.+\bписа[л](?:\(а\)|а)?:\s*$", re.IGNORECASE | re.MULTILINE),
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

# HTML quote-header (SOGo / Mail.ru-веб): текст-разделитель цитаты
# «писал(а):» / «писала:» / «писал:» (ru) или «wrote:» (en) внутри ``<p>``/``<div>``
# **перед** голым ``<blockquote>`` (без gmail_quote/moz-cite-prefix классов).
# Корпоративный webmail mail.mage.ru (SOGo) оборачивает процитированное письмо в
# ``<blockquote><div><figure class="table">...#N — тема...</figure></div></blockquote>``,
# а над ним ставит строку-разделитель в ``<p>`` (часто с датой/отправителем):
#   ``<p>Ответ<br>Четверг, ..., it@mage.ru писал(а):<br>&nbsp;</p><blockquote>...``
# Берём с предшествующим открывающим ``<p>``/``<div>`` и захлопывающими
# inline-тегами/``<br>``/``&nbsp;`` после разделителя — чтобы отрезать блок
# целиком (как ``_HTML_OUTLOOK_HEADER_RE``). Сам ``<blockquote>`` НИЖЕ по потоку
# не трогается (легитимное форматирование) — отрезается именно по разделителю.
_HTML_SOGO_HEADER_RE = re.compile(
    r"(?:<p\b[^>]*>|<div\b[^>]*>)?\s*(?:<\w+\b[^>]*>\s*)*"
    r"[^<>]*\b(?:писа[л](?:\(а\)|а)?|wrote)\s*:\s*(?:</\w+>\s*)*"
    r"(?:<br\s*/?>\s*)*(?:&nbsp;\s*)*",
    re.IGNORECASE,
)

# HTML Original Message-маркер (Roundcube / Outlook-веб): forward/reply-разделитель
# «-----Original Message-----» / «----- Исходное сообщение -----» внутри ``<div>``/``<p>``.
# Roundcube webmail оформляет цитату как ``<div>-------- Исходное сообщение --------</div>``
# с последующими ``<div>От:</div><div>Дата:</div>...`` (без ``<b>`` и без quote-классов,
# поэтому ``_HTML_OUTLOOK_HEADER_RE`` и ``_HTML_QUOTE_RE`` её пропускают).
# HTML-аналог первого ``_QUOTE_PATTERNS`` (plain). Локализации ru/en — те же, что в plain.
_HTML_ORIGINAL_MESSAGE_RE = re.compile(
    r"(?:<div\b[^>]*>|<p\b[^>]*>)?\s*-{2,}\s*"
    r"(?:Original\s+Message|Исходн(?:ого|ое)\s+сообщени[ея]"
    r"|Оригинал(?:ьного|ьное)\s+сообщени[ея])\s*-{2,}",
    re.IGNORECASE,
)

# Наш собственный HTML-маркер. ``REPLY_MARKER_TOKEN`` — это видимый текст
# инструкции («Ответьте выше этой линии»), а не скрытый машинный токен: скрытые
# узлы (``font-size:0``/HTML-комментарии) ненадёжно переживают ответ в Outlook
# (Word-рендер их вырезает), видимый текст — переживает всегда.
#
# При цитировании почтовый клиент оборачивает фразу в теги (``<p class="MsoNormal">``,
# ``<strong>``) и может прилепить ``↩`` из иконки маркера. Regex ниже ловит
# «открывающую обёртку блока + фразу» с допуском inline-тегов между ними — но
# требует, чтобы обёртка начиналась с блочного тега (``<div``/``<p``/``<span``/
# ``<table``/``<hr``), что запрещает захватывать теги из тела ответа (там перед
# маркером всегда стоит закрывающий тег). ``strip_quoted_html`` дополнительно
# подчищает висячие открывающие теги в хвосте (см. ``_DANGLING_OPEN_TAGS_RE``).
_BLOCK_OPEN = r"<(?:div|p|span|table|td|th|hr)\b[^>]*>"
_OWN_MARKER_HTML_RE = re.compile(
    r"(?:" + _BLOCK_OPEN + r"\s*)*(?:<\w+\b[^>]*>\s*)*(?:↦|↩)?\s*"
    r"(?:<\w+\b[^>]*>\s*)*" + re.escape(REPLY_MARKER_TOKEN),
    re.IGNORECASE,
)

# Висячие открывающие теги в конце обрезанного HTML (например, ``<div><strong>``
# после отсечения по фразе маркера, если закрывающих тегов ниже уже нет).
# Удаляем их для чистого вывода.
_DANGLING_OPEN_TAGS_RE = re.compile(r"(<\w+\b[^>]*>\s*)+$")


def build_reply_marker_plain(ticket_number: int) -> str:
    """Маркер-разделитель для plain-text части исходящего письма (точка отсечения
    цитаты при ответе заявителя).

    ``REPLY_MARKER_TOKEN`` (= «Ответьте выше этой линии») — это видимый текст
    инструкции, он же служит якорем для ``strip_quoted_reply``. Переживает
    round-trip во всех клиентах (включая Outlook, вырезающий скрытые узлы).
    На отдельной строке, чтобы обрезка забирала блок целиком без хвостов.
    """
    return f"\n\n--- {REPLY_MARKER_TOKEN} ---\n[#TKT-{ticket_number}]\n---\n"


def build_reply_marker_html(ticket_number: int) -> str:
    """Маркер-разделитель для HTML-части: хорошо заметная плашка.

    ``REPLY_MARKER_TOKEN`` (= «Ответьте выше этой линии») — это видимый текст
    плашки и одновременно якорь для ``strip_quoted_html``: скрытые якоря
    (``font-size:0``/HTML-комментарии) ненадёжно переживают ответ в Outlook
    (Word-рендер их вырезает), видимый текст — всегда. Regex
    ``_OWN_MARKER_HTML_RE`` допускает обёртывающие теги и ``↩``, которыми
    почтовик оборачивает фразу при цитировании.

    Дизайн: увеличенные внутренние отступы (18px 20px), контрастная двойная
    линия (``#b8c2cc``) сверху и снизу, чуть более плотный фон ``#eef1f4`` — блок
    сразу бросается в глаза (точка, где пользователь пишет ответ).
    """
    return (
        f'<div style="margin:28px 0 0;padding:18px 20px;'
        "border-top:3px solid #b8c2cc;border-bottom:3px solid #b8c2cc;"
        "background:#eef1f4;"
        'color:#24292f;font-size:14px;line-height:1.6;">'
        f"<strong>↩ {REPLY_MARKER_TOKEN}</strong>"
        "<br>История переписки ниже будет скрыта автоматически."
        f"<br>[#TKT-{ticket_number}]"
        "</div>"
    )


def _ticket_fingerprint(text: str, ticket_number: int) -> bool:
    return any(
        token.casefold() in text.casefold()
        for token in (
            f"[#TKT-{ticket_number}]",
            f"TKT-{ticket_number}",
            f"#{ticket_number} —",
            f"#{ticket_number} -",
        )
    )


def _ticket_quote_start(
    text: str,
    matches: list[re.Match[str]],
    ticket_number: int,
) -> int | None:
    """Найти начало quote-блока нашего тикета, не захватив более ранний forward."""
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if not _ticket_fingerprint(text[match.start() : end], ticket_number):
            continue
        # Outlook часто ставит рядом два распознаваемых заголовка:
        # ``Original Message`` и затем ``From/Sent``. Fingerprint находится во
        # втором сегменте, но удалить надо и непосредственно предшествующий
        # разделитель. Через произвольный текст назад не расширяемся.
        if index > 0 and not text[matches[index - 1].end() : match.start()].strip():
            return matches[index - 1].start()
        return match.start()
    return None


def strip_quoted_reply(
    text: str,
    *,
    keep_forward: bool = False,
    ticket_number: int | None = None,
) -> str:
    """Обрезать цитату предыдущего письма из plain-text тела.

    Слои (по надёжности):
      1. Наш маркер ``REPLY_MARKER_TOKEN`` — режем строго по нему (всегда,
         даже при ``keep_forward``: маркер проставляется только исходящими
         письмами портала, его наличие = заявитель отвечает на наше письмо,
         даже если matching по Message-ID не сработал → цитату убрать).
      2. Эвристика ``_QUOTE_PATTERNS`` — режем по первому совпадению.
         Пропускается при ``keep_forward=True``: для **новой** заявки
         forward-блок (``-----Original Message-----`` / Outlook ``From:/Sent:`` /
         Gmail ``wrote:``) — это часто суть обращения (bounce, ошибка,
         пересланный контекст), а не цитата. Отрезание ломало такие заявки.

    Если ничего не найдено — возвращает ``text`` без изменений.
    """
    if not text:
        return text

    # SOGo / некоторые веб-клиенты кодируют русский текст в numeric entities
    # даже в text/plain («писал» → «&#1087;&#1088;&#1080;&#1089;&#1072;&#1083;»).
    # Декодируем перед match — regex ищут буквальный русский текст.
    text = _decode_numeric_entities(text)

    # 1. Наш маркер — самый надёжный слой. ``REPLY_MARKER_TOKEN`` («Ответьте выше
    # этой линии») стоит в начале строки блока (``--- Ответьте выше этой линии ---``),
    # поэтому режем от начала этой строки, захватывая предшествующие пустые строки.
    idx = text.find(REPLY_MARKER_TOKEN)
    if idx >= 0:
        line_start = text.rfind("\n", 0, idx)
        cut = line_start + 1 if line_start >= 0 else 0
        kept = text[:cut].rstrip()
        return kept or text  # пустой ответ выше маркера → вернуть как есть

    # 2. Эвристика: первое (самое раннее) совпадение паттерна цитаты.
    # Для новых заявок (keep_forward=True) пропускаем — forward-блок
    # может быть сутью обращения (см. docstring).
    if keep_forward:
        return text

    matches = sorted(
        (match for pattern in _QUOTE_PATTERNS for match in pattern.finditer(text)),
        key=lambda match: match.start(),
    )
    if ticket_number is not None:
        # Для реального ingress режем только тот quote-блок, где есть точный
        # fingerprint нашего тикета. Ambiguous forward без fingerprint сохраняем.
        ticket_start = _ticket_quote_start(text, matches, ticket_number)
        earliest = ticket_start if ticket_start is not None else len(text)
    else:
        earliest = matches[0].start() if matches else len(text)
    if earliest < len(text):
        kept = text[:earliest].rstrip()
        return kept or text
    return text


def strip_quoted_html(
    html: str,
    *,
    keep_forward: bool = False,
    ticket_number: int | None = None,
) -> str:
    """Обрезать цитату предыдущего письма из HTML-тела.

    Многослойная обрезка (каждый слой работает с результатом предыдущего):
      1. Наш маркер ``REPLY_MARKER_TOKEN`` (видимый текст «Ответьте выше этой
         линии») — отрезает reply-маркер + историю под ним. При цитировании
         почтовый клиент оборачивает фразу в теги (``<p class="MsoNormal">``,
         ``<strong>``) и может прилепить ``↩`` из иконки маркера, поэтому
         ``_OWN_MARKER_HTML_RE`` допускает предшествующие теги/``↩``/``<hr>``.
         Применяется всегда (даже при ``keep_forward``): маркер проставляется
         только исходящими письмами портала, его наличие = заявитель отвечает
         на наше письмо, даже если matching не сработал → цитату убрать.
      2. Outlook quote-header ``<b>From:</b>`` / ``<b>От:</b>`` — отрезает
         процитированный ответ агента над маркером. **Пропускается при
         ``keep_forward=True``** (новая заявка — forward может быть сутью
         обращения, см. ``strip_quoted_reply``).
      3. HTML quote-контейнеры почтовых клиентов (``gmail_quote`` и т.п.).
         **Пропускается при ``keep_forward=True``** (та же причина).

    Универсальный ``<blockquote>`` без классов не трогает — это легитимное
    форматирование. Точная обрезка сбалансированных тегов не реализуется:
    quote-блок — почти всегда терминальный, поэтому отсечение от его начала
    до конца строки безопасно.

    Вызывается из ingress ``_extract_bodies`` на **сыром** письме (до ``nh3``):
    некоторые веб-клиенты (SOGo) кодируют русский текст в numeric entities
    (``&#1087;&#1080;&#1089;&#1072;&#1083;`` = «писал»), которые regex не
    матчат. Numeric entities декодируются на входе (``_decode_numeric_entities``);
    именованные (``&lt;``/``&gt;``/``&nbsp;``) сохраняются — они структурно
    значимы для regex (email в ``&lt; &gt;``, разделители).
    """
    if not html:
        return html

    # SOGo / некоторые веб-клиенты кодируют русский текст в numeric entities.
    # Декодируем перед regex-матчингом (именованные entities не трогаем —
    # см. ``_decode_numeric_entities``).
    kept = _decode_numeric_entities(html)

    # 1. Наш маркер (отрезает маркер + историю). Regex стартует с открывающего
    # блочного тега обёртки (запрещает захватывать теги из тела ответа).
    m = _OWN_MARKER_HTML_RE.search(kept)
    if m:
        kept = kept[: m.start()].rstrip()
        # Подчистить висячие открывающие теги в хвосте (например, ``<div><strong>``
        # если закрывающих тегов маркера ниже уже нет после обрезки).
        kept = _DANGLING_OPEN_TAGS_RE.sub("", kept).rstrip()

    if keep_forward:
        # Новая заявка: forward-блок (Outlook From:/Sent:, gmail_quote, …) —
        # часто суть обращения (bounce/ошибка/пересланный контекст), не цитата.
        return kept or html

    matches = sorted(
        (
            match
            for pattern in (
                _HTML_OUTLOOK_HEADER_RE,
                _HTML_SOGO_HEADER_RE,
                _HTML_ORIGINAL_MESSAGE_RE,
                _HTML_QUOTE_RE,
            )
            for match in pattern.finditer(kept)
        ),
        key=lambda match: match.start(),
    )
    if ticket_number is not None:
        ticket_start = _ticket_quote_start(kept, matches, ticket_number)
        if ticket_start is not None:
            kept = kept[:ticket_start].rstrip()
    elif matches:
        kept = kept[: matches[0].start()].rstrip()

    return kept or html
