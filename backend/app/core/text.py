"""Общие утилиты для работы с текстом."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, *, fallback: str = "item", preserve_unicode: bool = True) -> str:
    """Создаёт URL-совместимый slug из произвольного текста.

    Args:
        text: Исходная строка.
        fallback: Значение при пустом результате.
        preserve_unicode: Сохранять кириллицу/Unicode (True по умолчанию).
                         False — транслитерирует в ASCII.
    """
    if preserve_unicode:
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    else:
        norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()

    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or fallback
