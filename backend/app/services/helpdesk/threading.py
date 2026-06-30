"""Email-threading helpers for helpdesk ingress (ТЗ §1.3.8, §5.1).

Два независимых способа сопоставить входящее письмо с существующим тикетом:

1. **По ``In-Reply-To`` / ``References``** (основной, RFC 5322) — ищем в
   ``helpdesk_messages.email_message_id``. Исходящие ``Message-ID`` имеют
   канонический формат ``<tkn-{number}-{uuid}@{support_domain}>`` (§1.3.3),
   входящие ``Message-ID`` сохраняются в это же поле при приёме.
2. **По токену ``[#TKT-{number}]`` в ``Subject``** (fallback) — на случай,
   если почтовик клиента оборвал ``In-Reply-To`` / ``References``.

Письма без ``Message-ID`` получают synthetic id (§1.3.8) для идемпотентности.
Анти-loop-признаки (``Auto-Submitted``, ``Precedence`` и т.п.) — в ``ingress``.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from email.message import Message

# [#TKT-123] в теме (с опциональными пробелами). Fallback matching.
_SUBJECT_TOKEN_RE = re.compile(r"\[#TKT-(\d+)\]")


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
