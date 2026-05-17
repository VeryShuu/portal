"""Unit-тесты для apply_phone_regex."""

from __future__ import annotations

from app.utils.phone import apply_phone_regex


def test_regex_with_capture_group_returns_first_group():
    assert apply_phone_regex("+7-495-1234567", r"^\+7-(\d{3})") == "495"


def test_regex_without_group_returns_full_match():
    assert apply_phone_regex("tel 12345", r"\d+") == "12345"


def test_invalid_regex_returns_original_string():
    assert apply_phone_regex("12345", r"[") == "12345"


def test_empty_phone_returns_empty():
    assert apply_phone_regex("", r"\d+") == ""


def test_empty_pattern_returns_original():
    assert apply_phone_regex("12345", "") == "12345"


def test_no_match_returns_original():
    assert apply_phone_regex("abcdef", r"\d+") == "abcdef"
