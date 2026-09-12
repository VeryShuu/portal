"""Tests for the keyset-cursor helpers (audit M2).

Cursor — opaque base64url-строка, кодирующая ``created_at|id``. Тестируем
кодирование/декодирование, fallback на мусор, и SQL-фрагмент для keyset-WHERE.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api._cursor_pagination import cursor_clause, decode_cursor, encode_cursor


def test_encode_decode_roundtrip_int_id():
    """audit_log.id — BIGSERIAL (int): roundtrip сохраняет created_at + id."""
    ca = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    token = encode_cursor(ca, 12345)
    decoded = decode_cursor(token)
    assert decoded is not None
    assert decoded.created_at == ca
    assert decoded.id == "12345"


def test_encode_decode_roundtrip_uuid_id():
    """email_outbox.id — UUID: roundtrip сохраняет UUID как строку."""
    ca = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    token = encode_cursor(ca, uuid_str)
    decoded = decode_cursor(token)
    assert decoded is not None
    assert decoded.created_at == ca
    assert decoded.id == uuid_str


def test_decode_invalid_cursor_returns_none_for_fallback():
    """Мусорный cursor → None (fallback в OFFSET, не 400). UX-friendly."""
    assert decode_cursor("not-a-valid-base64!!") is None
    assert decode_cursor("") is None
    assert decode_cursor("||||") is None
    # Валидный base64, но не содержит разделитель '|'.
    import base64

    junk = base64.urlsafe_b64encode(b"no-pipe-here").decode("ascii").rstrip("=")
    assert decode_cursor(junk) is None


def test_cursor_is_opaque_no_leading_structure():
    """Cursor не должен содержать читаемый 'created_at|id' (opaque для клиента)."""
    ca = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    token = encode_cursor(ca, 42)
    assert "2026" not in token
    assert "|" not in token


def test_cursor_clause_returns_tuple_comparison():
    """SQL-фрагмент — tuple-comparison (canonical keyset для ORDER BY DESC)."""
    ca = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    sql, params = cursor_clause(type("C", (), {"created_at": ca, "id": "99"})())
    assert sql == "(created_at, id) < (:cursor_ca, :cursor_id)"
    assert params["cursor_ca"] == ca
    assert params["cursor_id"] == "99"


def test_different_timestamps_produce_different_cursors():
    """Две страницы с разными последними элементами → разные курсоры."""
    ca1 = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    ca2 = datetime(2026, 8, 2, 12, 1, tzinfo=UTC)
    assert encode_cursor(ca1, 1) != encode_cursor(ca2, 1)
    assert encode_cursor(ca1, 1) != encode_cursor(ca1, 2)
