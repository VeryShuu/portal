"""Email-threading helpers for helpdesk ingress (ТЗ §1.3.8, §5.1).

Два независимых способа сопоставить входящее письмо с существующим тикетом:

1. **По ``In-Reply-To`` / ``References``** (основной, RFC 5322) — ищем в
   ``helpdesk_messages.email_message_id``. Исходящие ``Message-ID`` имеют
   канонический формат ``<tkn-{number}-{uuid}@{support_domain}>`` (§1.3.3),
   входящие ``Message-ID`` сохраняются в это же поле при приёме.
2. **По токену ``[#TKT-{number}]`` в ``Subject``** (fallback) — на случай,
   если почтовик клиента оборвал ``In-Reply-To`` / ``References``.
3. **По plus-маркеру ``+TKT-{number}`` в адресе получателя** (опциональный
   fallback) — сканируем ``Delivered-To`` / ``X-Original-To`` / ``To``.
   Помогает, если ни заголовки threading'а, ни тема не сохранились
   (например, MUA переформулировал тему). Plus-маркер не проставляется
   исходящими письмами портала (``Reply-To`` использует чистый
   ``support_address``), но может встречаться при ручных пересылках или
   внешних автоответчиках; отсутствие маркера — норма, ``None``.

Письма без ``Message-ID`` получают synthetic id (§1.3.8) для идемпотентности.
Анти-loop-признаки (``Auto-Submitted``, ``Precedence`` и т.п.) — в ``ingress``.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from email.header import decode_header, make_header
from email.message import Message

# [#TKT-123] в теме (с опциональными пробелами). Fallback matching.
_SUBJECT_TOKEN_RE = re.compile(r"\[#TKT-(\d+)\]")

# plus-маркер в адресе получателя: local+TKT-123@domain. Опциональный fallback
# matching (см. extract_recipient_token). ``+TKT-`` — без скобок, т.к. это
# sub-address (RFC 5233), а не тег темы.
_RECIPIENT_TOKEN_RE = re.compile(r"\+TKT-(\d+)@")
# Заголовки адреса получателя в порядке надёжности: Delivered-To ставит
# принимающий MTA (точный envelope), X-Original-To — алиасы/форварды, To —
# автор (может быть подменён/отредактирован клиентом).
_RECIPIENT_HEADERS = ("Delivered-To", "X-Original-To", "To")


def decode_mime_header(raw: str | None) -> str:
    """Декодировать заголовок письма (RFC 2047 encoded-words).

    ``email.message.Message.get()`` при дефолтной политике ``compat32``
    возвращает заголовок «как есть» — с нераскрытыми ``=?charset?B?...?=`` /
    ``=?charset?Q?...?=`` (типично для кириллических ``Subject``/``From`` в
    кодировке KOI8-R/Windows-1251). Без декодирования тема тикета сохраняется
    в БД как ``=?koi8-r?B?zsUg...?=`` и так же отображается в UI.

    Некорректные encoded-words декодируются насколько возможно (errors=«replace»),
    полностью нераспознанные — возвращаются как есть.
    """
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def extract_message_id(msg: Message) -> str | None:
    """RFC 5322 Message-ID входящего письма (нормализованный, с угловыми скобками)."""
    raw = msg.get("Message-ID") or msg.get("Message-Id")
    if not raw:
        return None
    value = raw.strip().split()[0] if raw.strip() else ""
    if not value:
        return None
    if not value.startswith("<"):
        value = f"<{value}"
    if not value.endswith(">"):
        value = f"{value}>"
    return value


def extract_references(msg: Message) -> list[str]:
    """Список Message-ID из ``In-Reply-To`` + ``References`` (для matching'а
    по цепочке). Дедуплицированный, порядок сохранён."""
    seen: set[str] = set()
    result: list[str] = []
    for header in ("In-Reply-To", "References"):
        raw = msg.get(header)
        if not raw:
            continue
        for token in raw.split():
            token = token.strip()
            if token and token not in seen:
                seen.add(token)
                result.append(token)
    return result


def extract_subject_token(subject: str | None) -> int | None:
    """Извлечь ``number`` из ``[#TKT-{number}]`` в теме (fallback matching).
    Возвращает ``None``, если токена нет."""
    if not subject:
        return None
    m = _SUBJECT_TOKEN_RE.search(subject)
    return int(m.group(1)) if m else None


def strip_subject_token(subject: str) -> str:
    """Убрать ``[#TKT-{number}]`` из темы (для хранения чистой темы тикета).

    Токен добавляется исходящими письмами портала; во входящем ответе он не
    нужен (матчинг уже выполнен). Используется в ingress ``_derive_subject``
    вместо прямого доступа к приватному ``_SUBJECT_TOKEN_RE``."""
    return _SUBJECT_TOKEN_RE.sub("", subject or "").strip()


def extract_recipient_token(msg: Message) -> int | None:
    """Извлечь ``number`` из plus-маркера ``+TKT-{number}@`` в адресе
    получателя (опциональный fallback matching).

    Сканирует заголовки ``Delivered-To`` → ``X-Original-To`` → ``To`` (в порядке
    надёжности). Каждый заголовок может содержать несколько адресов через
    запятую (``a@x, b@y``); берётся первый матч. Возвращает ``None``, если ни в
    одном адресе маркера нет — это норма, т.к. портал не проставляет plus-маркер
    в исходящем ``Reply-To`` (используется чистый ``support_address``).
    """
    for header in _RECIPIENT_HEADERS:
        for raw in msg.get_all(header) or []:
            if not raw:
                continue
            m = _RECIPIENT_TOKEN_RE.search(raw)
            if m:
                return int(m.group(1))
    return None


def extract_cc(msg: Message, *, exclude: str | None = None) -> list[dict[str, str | None]]:
    """Список адресатов из заголовка ``Cc`` входящего письма (миграция 083).

    Возвращает ``[{"email": "a@x", "name": "Иван"}, ...]`` — нормализованный,
    дедуплицированный (по lowercased email). Порядок сохранён (как в письме).
    ``name`` — декодированный display-name (RFC 2047, как ``decode_mime_header``
    для ``Subject``/``From``); ``None`` для голого ``user@host`` без имени.

    ``exclude`` — email, который выкинуть из результата (case-insensitive).
    Используется ingress'ом для отсечения ``support_address``: иначе агент,
    ответив «всем», отправит копию в ящик поддержки → письмо вернётся в IMAP →
    петля/дубль тикета (``is_from_self`` сработает на anti-loop, но поддержка
    в копии своей же переписки — бессмысленно и засоряет инбокс оператора).

    Пустой список, если заголовка ``Cc`` нет или он пустой. ``Bcc`` не парсим —
    он по определению невидим получателю (RFC 5322), и в письмах заявителя его
    не бывает в осмысленном виде.
    """
    from email.utils import getaddresses

    raw_values = msg.get_all("Cc", [])
    if not raw_values:
        return []
    participants: list[dict[str, str | None]] = []
    seen: set[str] = set()
    exclude_lc = (exclude or "").strip().lower()
    for name, addr in getaddresses(raw_values):
        email = (addr or "").strip().lower()
        if not email or "@" not in email:
            continue
        if email == exclude_lc:
            continue
        if email in seen:
            continue
        seen.add(email)
        decoded_name = (decode_mime_header(name) if name else "").strip()
        participants.append({"email": email, "name": decoded_name or None})
    return participants


def synthetic_message_id(
    *, mailbox: str, uid: int | str, date: str, sender: str, subject: str, size: int
) -> str:
    """Stable id для писем без ``Message-ID`` (ТЗ §1.3.8): идемпотентность при
    повторном скачивании того же письма. Формат:
    ``<synthetic:{sha256(mailbox, uid, date, from, subject, size)}>``
    """
    payload = f"{mailbox}|{uid}|{date}|{sender}|{subject}|{size}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"<synthetic:{digest}>"


def normalize_email(raw: str | None) -> str:
    """Извлечь и нормализовать email-адрес из ``From``-заголовка
    (``"Name" <user@host>`` → ``user@host``, lowercase+strip)."""
    if not raw:
        return ""
    # Самый правый ``<...>`` — адрес; иначе берём последний токен с @.
    m = re.search(r"<([^<>]+@[^<>]+)>", raw)
    if m:
        return str(m.group(1)).strip().lower()
    for token in re.findall(r"[\w.+-]+@[\w.-]+", raw):
        return str(token).strip().lower()
    return ""


def extract_display_name(raw: str | None) -> str | None:
    """Имя отправителя из ``From`` (часть до ``<addr>``), если есть."""
    if not raw:
        return None
    m = re.match(r'^\s*"?([^"<]+?)"?\s*<', raw)
    return m.group(1).strip() if m else None


def is_outbound_message_id(message_id: str | None) -> bool:
    """Признак того, что Message-ID принадлежит исходящему helpdesk-письму
    (формат ``<tkn-...>``). Используется для matching'а входящего ответа."""
    return bool(message_id and message_id.startswith("<tkn-"))


def parse_outbound_message_id(message_id: str | None) -> tuple[int, uuid.UUID] | None:
    """Разобрать исходящий Message-ID ``<tkn-{number}-{uuid}@{domain}>`` →
    ``(number, message_uuid)``. ``None`` для не-канонических id."""
    if not message_id:
        return None
    m = re.match(r"^<tkn-(\d+)-([0-9a-fA-F-]{36})@", message_id)
    if not m:
        return None
    return int(m.group(1)), uuid.UUID(m.group(2))
