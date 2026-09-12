"""Helpers for cross-layout text search (QWERTY <-> ЙЦУКЕН)."""

from __future__ import annotations

_EN_TO_RU_PAIRS = (
    ("q", "й"),
    ("w", "ц"),
    ("e", "у"),
    ("r", "к"),
    ("t", "е"),
    ("y", "н"),
    ("u", "г"),
    ("i", "ш"),
    ("o", "щ"),
    ("p", "з"),
    ("[", "х"),
    ("]", "ъ"),
    ("a", "ф"),
    ("s", "ы"),
    ("d", "в"),
    ("f", "а"),
    ("g", "п"),
    ("h", "р"),
    ("j", "о"),
    ("k", "л"),
    ("l", "д"),
    (";", "ж"),
    ("'", "э"),
    ("z", "я"),
    ("x", "ч"),
    ("c", "с"),
    ("v", "м"),
    ("b", "и"),
    ("n", "т"),
    ("m", "ь"),
    (",", "б"),
    (".", "ю"),
    ("/", "."),
    ("`", "ё"),
)


def _build_translation_tables() -> tuple[dict[int, str], dict[int, str]]:
    en_to_ru: dict[int, str] = {}
    ru_to_en: dict[int, str] = {}
    for en, ru in _EN_TO_RU_PAIRS:
        en_to_ru[ord(en)] = ru
        en_to_ru[ord(en.upper())] = ru.upper()
        ru_to_en[ord(ru)] = en
        ru_to_en[ord(ru.upper())] = en.upper()
    return en_to_ru, ru_to_en


_EN_TO_RU_TABLE, _RU_TO_EN_TABLE = _build_translation_tables()


def en_to_ru(text: str) -> str:
    """Translate Latin characters typed on a QWERTY keyboard into their
    ЙЦУКЕН equivalents. Characters absent in the map are kept as-is."""
    return text.translate(_EN_TO_RU_TABLE)


def ru_to_en(text: str) -> str:
    """Inverse of :func:`en_to_ru`."""
    return text.translate(_RU_TO_EN_TABLE)


def layout_variants(text: str) -> list[str]:
    """Return a list of layout variants for ``text``.

    Always includes the original string. Adds an EN→RU conversion when the
    string contains Latin letters, and an RU→EN conversion when it contains
    Cyrillic letters. Useful for fuzzy search when the user forgot to
    switch keyboard layout.
    """
    if not text:
        return []
    variants: list[str] = [text]
    seen: set[str] = {text}

    has_latin = any("a" <= ch.lower() <= "z" for ch in text)
    has_cyrillic = any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in text)

    if has_latin:
        converted = en_to_ru(text)
        if converted not in seen:
            variants.append(converted)
            seen.add(converted)
    if has_cyrillic:
        converted = ru_to_en(text)
        if converted not in seen:
            variants.append(converted)
            seen.add(converted)
    return variants
