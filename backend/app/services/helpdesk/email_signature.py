"""Отсечение корпоративной email-подписи из входящих helpdesk-писем.

Подпись генерируется нашим сервисом ``app.services.signature.render_signature``
(см. ``backend/app/services/signature.py``): таблица с логотипом Mage_Ru.png +
ФИО/должность/телефоны/email в фирменных цветах (#00479D / #9E9E9E). Все письма
сотрудников интранет-портала (~300 чел.) приходят с этой подписью.

Без отсечения подпись попадает в ``helpdesk_messages.body_text`` и в MAX-
уведомление о новой заявке (заголовок «Заявка от ФИО» + «Текст заявки:»
засоряется блоком «Руководитель отдела / +7 ... / borzihin.vs@mage.ru»).

Подход — preservation-first: новые подписи имеют явный marker, legacy-подписи
распознаются только по согласованным признакам внутри одного HTML-контейнера:

1. ``<img ... src=".../Mage_Ru.png" ...>`` — логотип. Самый надёжный маркер.
2. ``border(-right)?:solid #7B92AE`` — стиль ячейки-разделителя (логотип | текст).
3. ``color:#00479D`` / ``color: #00479D`` — фирменный синий ФИО.
4. ``mailto:...@mage.ru`` в ``<a>``, окружённом стилем подписи.

Одиночный цвет/mailto/border недостаточен. Удаляется ровно контейнер подписи,
а не хвост письма: после подписи может идти важный forward.

Ограничения (осознанные):
- Неуверенно распознанная подпись сохраняется: лишний текст обратим, потеря
  пользовательского контекста — нет.
- Подписи сторонних доменов не удаляются без стандартного plain delimiter.

Генератор ``render_signature`` ставит
``data-portal-email-signature="mage-v1"`` для PC/Apple/Web/Phone. Legacy HTML
поддерживается по известному table-layout без миграции сохранённых сообщений.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

# ─── Company-specific маркеры подписи ─────────────────────────────────────────
# TODO(owner: IT / branding): при ребрендинге, смене шаблона подписи, фирменных
# цветов или домена — обновить эти константы. Они захардкожены, потому что
# мы авторы шаблона подписи (``app.services.signature``) и точно знаем его
# структуру. Источник: ``backend/app/services/signature.py`` (render_signature).
# Если изменится домен/email/логотип/цвет — эвристика ``strip_email_signature``
# молча перестанет отрезать подпись у ВСЕХ сотрудников (~300 чел.), и подписи
# снова начнут попадать в bodies/MAX-уведомления (см. баг от 20.07.2026).
SIGNATURE_LOGO_FILENAMES = ("Mage_Ru.png", "Mage_Eng.png", "WebRu.png", "WebEng.png")
SIGNATURE_BORDER_COLOR = "#7B92AE"
SIGNATURE_BLUE_COLOR = "#00479D"
# Домены корпоративной почты (для mailto-маркера). ``portal-svc`` — service
# account (App Password для Nextcloud, см. ADR-032), тоже часть подписи.
SIGNATURE_EMAIL_DOMAINS = ("mage.ru", "portal-svc")

# Компилируем один раз при импорте (как ``_QUOTE_PATTERNS`` в ``email_quote``).

# 1. Логотип Mage_Ru.png (в любом регистре, любой путь до имени файла).
#    Outlook оборачивает ``src`` в кавычки/без, добавляет ``id=``, ``width=``,
#    ``height=`` — поэтому паттерн ищет только ``src=".../Mage_Ru.png"``.
_SIGNATURE_LOGO_RE = re.compile(
    rf"""<img\b[^>]*\bsrc\s*=\s*["'][^"']*/?(?:{
        "|".join(re.escape(name) for name in SIGNATURE_LOGO_FILENAMES)
    })["']""",
    re.IGNORECASE,
)

# 2. Ячейка-разделитель с фирменным цветом границы ``solid #7B92AE``.
#    Outlook любит ``border-right:solid #7B92AE 1.0pt`` (без пробелов),
#    генератор — ``border-right: solid 1px #7B92AE`` (пробелы). Допускаем оба.
_SIGNATURE_BORDER_RE = re.compile(
    rf"""border(?:-right|-left|-top|-bottom)?\s*:\s*(?:\d+(?:\.\d+)?(?:px|pt)\s+)?solid\s+(?:\d+(?:\.\d+)?(?:px|pt)\s+)?{re.escape(SIGNATURE_BORDER_COLOR)}""",
    re.IGNORECASE,
)

# 3. Фирменный синий ФИО ``color:#00479D``. Outlook иногда вставляет ``;`` после,
#    генератор — без. Ищем в любом ``style="..."``.
#    Character class ``[47]`` на 3-й позиции цвета — намеренная толерантность
#    к легаси-варианту ``#00779D`` (опечатка в ранних шаблонах подписи). Сам
#    канонический цвет — ``SIGNATURE_BLUE_COLOR`` выше.
_SIGNATURE_BLUE_RE = re.compile(
    r"""color\s*:\s*(?:#00[47]79[Dd]|rgb\(\s*0\s*,\s*(?:71|119)\s*,\s*157\s*\))""",
    re.IGNORECASE,
)

# 4. Mailto-ссылка на корпоративный домен — финальный маркер (email в подписи).
#    Подпись всегда заканчивается ``<a href="mailto:...@mage.ru">``.
_SIGNATURE_DOMAINS_ALT = "(?:{})".format("|".join(re.escape(d) for d in SIGNATURE_EMAIL_DOMAINS))
_SIGNATURE_MAILTO_RE = re.compile(
    rf"""<a\b[^>]*\bhref\s*=\s*["']mailto:[^"']*@{_SIGNATURE_DOMAINS_ALT}(?:\?[^"']*)?["']""",
    re.IGNORECASE,
)
_CID_IMG_RE = re.compile(
    r"""<img\b[^>]*\bsrc\s*=\s*(?:["']cid:([^"']+)["']|cid:([^\s>]+))""",
    re.IGNORECASE,
)

# Явный marker новых шаблонов и допустимые структурные контейнеры.
_EXPLICIT_SIGNATURE_RE = re.compile(
    r"\bdata-portal-email-signature\s*=\s*[\"']mage-v1[\"']",
    re.IGNORECASE,
)
_SIGNATURE_CONTAINER_TAGS = frozenset({"address", "div", "section", "table"})
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_PLAIN_SIGNOFF_RE = re.compile(
    r"(?im)^(?:-- |с уважением[,!]?|best regards[,!]?|kind regards[,!]?|regards[,!]?)\s*$"
)
_PLAIN_FORWARD_RE = re.compile(
    r"(?im)^\s*(?:-{2,}\s*(?:original message|исходн(?:ого|ое) сообщени[ея])\s*-{2,}"
    r"|(?:from|от):\s.+\n\s*(?:sent|отправлено):"
    r"|on\s.+\bwrote:\s*$|.+\b(?:написа[л](?:\(а\)|а)?|писа[л](?:\(а\)|а)?)\s*:\s*$)"
)
_PLAIN_CONTACT_RE = re.compile(
    r"(?i)(?:\b[\w.+-]+@(?:[\w-]+\.)+[\w-]+\b|\bwww\.mage\.ru\b|(?:\+?7|8)[\s(.-]*\d)"
)


@dataclass(slots=True)
class _HtmlNode:
    tag: str
    start: int
    end: int


class _SignatureHtmlParser(HTMLParser):
    """Минимальный tolerant parser, сохраняющий offsets исходной HTML-строки."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.nodes: list[_HtmlNode] = []
        self._stack: list[_HtmlNode] = []
        self._line_offsets = [0]
        for match in re.finditer("\n", source):
            self._line_offsets.append(match.end())

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        start = self._offset()
        raw = self.get_starttag_text() or ""
        node = _HtmlNode(tag=tag.lower(), start=start, end=start + len(raw))
        self.nodes.append(node)
        if node.tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack and self._stack[-1].tag == tag.lower():
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        end_start = self._offset()
        closing = self.source.find(">", end_start)
        end = len(self.source) if closing < 0 else closing + 1
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                for node in self._stack[index:]:
                    node.end = end
                del self._stack[index:]
                return

    def close(self) -> None:
        super().close()
        for node in self._stack:
            node.end = len(self.source)
        self._stack.clear()


def _contains_position(positions: list[int], start: int, end: int) -> bool:
    index = bisect_left(positions, start)
    return index < len(positions) and positions[index] < end


def _is_signature_container(
    node: _HtmlNode,
    *,
    explicit: list[int],
    logos: list[int],
    borders: list[int],
    blues: list[int],
    mailtos: list[int],
) -> bool:
    """Проверить согласованные признаки по заранее собранным offsets."""
    if _contains_position(explicit, node.start, node.end):
        return True
    has_logo = _contains_position(logos, node.start, node.end)
    weak_signals = sum(
        _contains_position(positions, node.start, node.end)
        for positions in (borders, blues, mailtos)
    )
    # Старые PC/Apple/Web-подписи всегда табличные. Точный логотип в таблице —
    # сильный признак; без логотипа требуем полный набор из трёх слабых маркеров.
    return (node.tag == "table" and has_logo) or weak_signals == 3


def is_known_signature_asset_name(value: str) -> bool:
    """Whether a MIME filename/Content-Location identifies our logo asset."""

    parsed = urlparse(value)
    name = PurePosixPath(unquote(parsed.path or value)).name.lower()
    return name in {filename.lower() for filename in SIGNATURE_LOGO_FILENAMES}


def _mime_logo_positions(html: str, cid_names: dict[str, tuple[str, ...]]) -> list[int]:
    positions: list[int] = []
    for match in _CID_IMG_RE.finditer(html):
        cid = (match.group(1) or match.group(2) or "").strip().strip("<>").lower()
        if any(is_known_signature_asset_name(name) for name in cid_names.get(cid, ()) if name):
            positions.append(match.start())
    return positions


def _signature_ranges(
    html: str,
    *,
    cid_names: dict[str, tuple[str, ...]] | None = None,
) -> list[tuple[int, int]]:
    parser = _SignatureHtmlParser(html)
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return []

    # Каждый regex проходит письмо один раз. Проверка контейнера затем использует
    # binary search по offsets и не пересканирует вложенные HTML-фрагменты.
    signal_positions = {
        "explicit": [match.start() for match in _EXPLICIT_SIGNATURE_RE.finditer(html)],
        "logos": [match.start() for match in _SIGNATURE_LOGO_RE.finditer(html)]
        + _mime_logo_positions(html, cid_names or {}),
        "borders": [match.start() for match in _SIGNATURE_BORDER_RE.finditer(html)],
        "blues": [match.start() for match in _SIGNATURE_BLUE_RE.finditer(html)],
        "mailtos": [match.start() for match in _SIGNATURE_MAILTO_RE.finditer(html)],
    }
    candidates = [
        node
        for node in parser.nodes
        if node.tag in _SIGNATURE_CONTAINER_TAGS
        and node.end > node.start
        and _is_signature_container(node, **signal_positions)
    ]
    # Берём минимальные подходящие контейнеры: внешний wrapper не нужен, если
    # внутри уже найден точный signature-table. Перекрывающиеся ranges удаляем.
    candidates.sort(key=lambda node: (node.end - node.start, node.start))
    selected: list[_HtmlNode] = []
    for node in candidates:
        if any(other.start >= node.start and other.end <= node.end for other in selected):
            continue
        selected.append(node)
    return sorted((node.start, node.end) for node in selected)


def strip_email_signature(
    html: str | None,
    *,
    cid_names: dict[str, tuple[str, ...]] | None = None,
) -> str | None:
    """Отрезать корпоративную подпись из HTML-тела письма.

    Удаляет только уверенно распознанные HTML-контейнеры подписи. Контент после
    контейнера сохраняется: это критично для forward, где порядок обычно такой:
    новый комментарий → подпись отправителя → пересланное сообщение.

    Одиночные слабые маркеры (``mailto:@mage.ru``, фирменный цвет, border) не
    считаются подписью: они легитимно встречаются в теле заявки. Для legacy-
    подписей требуется табличный контейнер с известным логотипом либо сочетание
    всех трёх слабых признаков; новые шаблоны имеют явный ``data-*`` marker.

    Возвращает обновлённый HTML или исходный, если ни один маркер не найден.
    ``None``/пустая строка → возвращаются как есть (идемпотентно).
    """
    if not html:
        return html
    ranges = _signature_ranges(html, cid_names=cid_names)
    if not ranges:
        return html
    chunks: list[str] = []
    cursor = 0
    for start, end in ranges:
        chunks.append(html[cursor:start])
        cursor = end
    chunks.append(html[cursor:])
    return "".join(chunks).strip()


def strip_plain_signature(text: str | None, *, preserve_forward: bool = False) -> str | None:
    """Консервативно удалить plain-подпись только из авторского сегмента.

    RFC 3676 delimiter ``-- `` и распространённые sign-off фразы считаются
    границей подписи. При forward подпись удаляется только до его начала, сам
    пересланный блок возвращается без изменений.
    """
    if not text:
        return text
    forward = _PLAIN_FORWARD_RE.search(text) if preserve_forward else None
    authored_end = forward.start() if forward else len(text)
    authored = text[:authored_end]
    matches = list(_PLAIN_SIGNOFF_RE.finditer(authored))
    if not matches:
        return text
    signature_start = matches[-1].start()
    # Формула вежливости без строк подписи после неё — обычный текст, не режем.
    signature_tail = authored[matches[-1].end() :].strip()
    if not signature_tail:
        return text
    delimiter = matches[-1].group().strip()
    if delimiter != "--" and _PLAIN_CONTACT_RE.search(signature_tail) is None:
        return text
    kept = authored[:signature_start].rstrip()
    preserved = text[authored_end:].lstrip() if forward else ""
    if kept and preserved:
        return f"{kept}\n\n{preserved}"
    return kept or preserved or text
