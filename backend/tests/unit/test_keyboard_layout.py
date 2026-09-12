"""Unit-тесты для keyboard_layout."""

from __future__ import annotations

from app.utils.keyboard_layout import en_to_ru, layout_variants, ru_to_en


def test_en_to_ru_basic():
    assert en_to_ru("Bdfyjd") == "Иванов"


def test_ru_to_en_basic():
    assert ru_to_en("Иванов") == "Bdfyjd"


def test_en_to_ru_preserves_non_letters():
    assert en_to_ru("Ivan 2024") == "Шмфт 2024"


def test_layout_variants_includes_original():
    assert "Иванов" in layout_variants("Иванов")


def test_layout_variants_latin_input_adds_ru():
    variants = layout_variants("Bdfyjd")
    assert "Bdfyjd" in variants
    assert "Иванов" in variants


def test_layout_variants_cyrillic_input_adds_en():
    variants = layout_variants("Иванов")
    assert "Иванов" in variants
    assert "Bdfyjd" in variants


def test_layout_variants_empty_string():
    assert layout_variants("") == []


def test_layout_variants_digits_only():
    assert layout_variants("12345") == ["12345"]


def test_layout_variants_no_duplicates():
    variants = layout_variants("123")
    assert variants == ["123"]
