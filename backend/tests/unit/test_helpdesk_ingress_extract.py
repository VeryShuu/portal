"""Unit-тесты ``_extract_rfc822`` — извлечение тела письма из FETCH-ответа.

Защита от регрессии бага, при котором ``aioimaplib`` отдаёт FETCH-данные
плоским списком ``[bytes, bytearray, bytes, bytes]``, а ``_extract_rfc822``
искал ``tuple`` (старый формат) → возвращал ``None`` → ``message_from_bytes``
падал с ``AttributeError`` → ingress помечал каждое письмо ``errors += 1``,
не создавая тикет.
"""

from __future__ import annotations

from app.services.helpdesk.ingress import _extract_rfc822

# Реалистичный ответ aioimaplib для FETCH (RFC822): плоский список.
_AIOIMAPLIB_RESPONSE = [
    b"1 FETCH (RFC822 {11}",
    bytearray(b"hello world"),
    b")",
    b"Fetch completed (0.001 secs).",
]


def test_extract_from_flat_aioimaplib_response() -> None:
    """Основной кейс: aioimaplib отдаёт плоский список с bytearray-телом."""
    assert _extract_rfc822(_AIOIMAPLIB_RESPONSE) == b"hello world"


def test_extract_picks_longest_bytes_element() -> None:
    """Среди нескольких bytes-элементов выбирается самый длинный (тело)."""
    data = [b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"), b")", b"OK"]
    assert _extract_rfc822(data) == b"BODY!"


def test_extract_from_tuple_format_legacy() -> None:
    """Совместимость со старым tuple-форматом (вдруг кто-то его отдаёт)."""
    data = [(b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"))]
    assert _extract_rfc822(data) == b"BODY!"


def test_extract_from_mixed_tuple_and_flat() -> None:
    # Плоская часть с литералом имеет приоритет; тело — элемент после маркера.
    data = [b"marker", b"1 FETCH (RFC822 {22}", b"FULL RFC822 BODY HERE", b")"]
    out = _extract_rfc822(data)
    assert out == b"FULL RFC822 BODY HERE"


def test_extract_returns_none_on_empty() -> None:
    assert _extract_rfc822([]) is None


def test_extract_returns_none_when_no_bytes() -> None:
    assert _extract_rfc822([None, 42, "str"]) is None


def test_extract_handles_bytes_and_bytearray() -> None:
    """Тело может прийти и как bytes, и как bytearray (варианты aioimaplib)."""
    assert _extract_rfc822([b"1 FETCH (RFC822 {5}", b"BODY!", b")"]) == b"BODY!"
    assert _extract_rfc822([b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"), b")"]) == b"BODY!"
