"""Keyset (cursor) pagination helpers shared across admin list endpoints.

audit M2: OFFSET-пагинация на растущих таблицах (audit_log, email_outbox) линейно
деградирует — ``OFFSET 10000`` сканирует и отбрасывает 10k строк. Keyset-курсор
``WHERE (created_at, id) < (:last_ca, :last_id)`` использует композитный индекс
``(created_at DESC, id DESC)`` за O(log n).

Cursor — opaque base64url-строка (для клиента — чёрный ящик). Кодирует
``created_at|id`` последнего элемента текущей страницы; клиент шлёт его обратно
как ``?cursor=`` и получает следующую страницу. ``offset`` сохранён для
backward-compat (когда cursor не передан — старый путь).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Cursor:
    """Декодированный курсор: координаты последней строки предыдущей страницы."""

    created_at: datetime
    id: int | str  # audit_log.id — BIGSERIAL (int); email_outbox.id — UUID (str)


def encode_cursor(created_at: datetime, row_id: int | str) -> str:
    """Упаковывает (created_at, id) в opaque base64url-строку.

    Формат ``created_at|id`` (pipe-разделитель). ISO-формат для created_at
    (timezone-aware). base64url — чтобы клиент не видел внутреннюю структуру
    и не пытался её редактировать (курсор — чёрный ящик).
    """
    raw = f"{created_at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Cursor | None:
    """Распаковывает cursor. Возвращает None при любом повреждении (fallback в OFFSET).

    None-возврат — осознанный fallback: если клиент прислал мусор/устаревший
    курсор, лечше отдать первую страницу через OFFSET, чем 400-ошибкой ломать UX.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        created_at_str, id_str = raw.rsplit("|", 1)
        created_at = datetime.fromisoformat(created_at_str)
        # id может быть int (audit_log BIGSERIAL) или UUID-строкой (email_outbox);
        # оба корректно сравниваются в SQL. Храним как строку, приведение у caller'а.
        return Cursor(created_at=created_at, id=id_str)
    except (ValueError, TypeError):
        return None


def cursor_clause(cursor: Cursor) -> tuple[str, dict[str, object]]:
    """Возвращает (SQL-фрагмент, bind-params) для keyset-WHERE.

    caller добавляет фрагмент в общий WHERE (с ведущим ``AND``). Использует
    tuple-comparison Postgres — canonical keyset-паттерн для составной сортировки
    ``ORDER BY created_at DESC, id DESC``.
    """
    return (
        "(created_at, id) < (:cursor_ca, :cursor_id)",
        {"cursor_ca": cursor.created_at, "cursor_id": cursor.id},
    )
