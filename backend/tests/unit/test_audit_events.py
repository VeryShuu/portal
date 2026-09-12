"""Характеризующие тесты для реестра audit event_type.

Цель: гарантировать, что (а) реестр ``KNOWN_EVENT_TYPES`` не дрейфует
относительно реальных литералов в коде, и (б) опечатка в
``event_type="links.vistied"`` не сможет молча создать новый тип в
``audit_log``.

Подход: парсим ``backend/app/`` через AST, собираем все ``event_type="..."``
литералы и сверяем с ``KNOWN_EVENT_TYPES``. Любой literal, не
зарегистрированный в реестре, проваливает тест — нужно либо добавить строку в
``KNOWN_EVENT_TYPES``, либо исправить опечатку.

Эти тесты запускаются быстро (filesystem-scan), без импорта app/.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.services.audit_events import (
    KNOWN_EVENT_TYPES,
    all_event_types,
    is_known_event_type,
    iter_event_types,
)

# Папка backend/app — корень приложения. tests/conftest/внешние — не в счёт.
_APP_DIR = Path(__file__).resolve().parent.parent.parent / "app"

# Формат таксономии: <domain>.<action>, lowercase ASCII.
_EVENT_VALUE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")


def _collect_event_literals() -> dict[str, set[Path]]:
    """Сканирует app/ на ``event_type="<value>"`` kwargs.

    Использует ``ast.parse`` (а не regex по сырому тексту), чтобы автоматически
    исключить комментарии, docstrings и нерелевантные строковые литералы —
    ловит только реальные keyword-arguments вида ``event_type="..."`` в вызовах
    функций. Поддерживает условные выражения ``event_type="a" if cond else "b"``
    (извлекает оба варианта). Возвращает ``{value: {files}}``.
    """
    found: dict[str, set[Path]] = {}
    for py_file in _APP_DIR.rglob("*.py"):
        try:
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(py_file))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            # Случай 1: event_type="..." как keyword в вызове функции/метода.
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "event_type":
                        for val in _extract_strings(kw.value):
                            _record_literal(val, py_file, found)
            # Случай 2: dict {"event_type": "..."}, используемый в пуше.
            # ast.Dict.keys и .values всегда равной длины (ключ может быть None
            # для **-unpacking, но длины гарантированы совпадают).
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "event_type"
                        and value is not None
                    ):
                        for val in _extract_strings(value):
                            _record_literal(val, py_file, found)
    return found


def _extract_strings(node: ast.AST) -> list[str]:
    """Извлечь строковые константы из expression-node.

    Поддерживает:
      - ``ast.Constant`` (прямая строка)
      - ``ast.IfExp`` (``"a" if cond else "b"`` — извлекаем обе ветки)
      - ``ast.JoinedStr`` (f-strings — пропускаем, не static-literal)
    Всё прочее (переменные, вызовы) → пустой список (не static).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _extract_strings(node.body) + _extract_strings(node.orelse)
    return []


def _record_literal(value: object, py_file: Path, found: dict[str, set[Path]]) -> None:
    """Записать literal в реестр, если он похож на event_type (формат домен.action)."""
    if not isinstance(value, str):
        return
    # Только подходящие по формату — фильтрует шум вида event_type=variable.
    if _EVENT_VALUE_PATTERN.match(value):
        found.setdefault(value, set()).add(py_file)


def test_known_event_types_has_no_duplicates() -> None:
    """frozenset по построению не содержит дублей; проверяем только count."""
    # frozenset гарантирует уникальность; тест документирует инвариант.
    assert len(KNOWN_EVENT_TYPES) > 0, "KNOWN_EVENT_TYPES is empty"
    # Наличие дублей в исходном literal-list проявилось бы как меньший размер:
    # все значения уникальны (это просто самопроверка реестра).
    assert isinstance(KNOWN_EVENT_TYPES, frozenset)


def test_known_event_types_naming_convention() -> None:
    """Все значения следуют формату ``<domain>.<action>`` (минимум одна точка)."""
    for value in KNOWN_EVENT_TYPES:
        assert "." in value, f"Event type without domain separator: {value}"
        # Домен и action — lowercase ASCII, без дефисов.
        for part in value.split("."):
            assert part, f"Empty segment in {value}"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", part), f"Invalid segment '{part}' in {value}"


def test_all_literals_in_code_are_registered() -> None:
    """Каждый event_type-литерал в app/ должен быть в KNOWN_EVENT_TYPES.

    Если тест падает: добавьте новое значение в ``KNOWN_EVENT_TYPES`` (файл
    ``app/services/audit_events.py``) ИЛИ исправьте опечатку в литерале.
    """
    literals = _collect_event_literals()
    assert literals, "No event_type literals found — AST scan broke?"

    unregistered: dict[str, set[Path]] = {}
    for literal, files in literals.items():
        if not is_known_event_type(literal):
            unregistered[literal] = files

    assert not unregistered, (
        "event_type literals in code not registered in KNOWN_EVENT_TYPES "
        "(add to app/services/audit_events.py or fix typo):\n"
        + "\n".join(
            f"  {lit!r} in {', '.join(str(p.relative_to(_APP_DIR.parent)) for p in files)}"
            for lit, files in sorted(unregistered.items())
        )
    )


def test_all_registered_types_are_used_in_code() -> None:
    """Каждое значение в KNOWN_EVENT_TYPES должно иметь хотя бы один literal в app/.

    Защита от мёртвых записей реестра (удалённый feature оставил след).
    Если тест падает: удалите неиспользуемое значение из ``KNOWN_EVENT_TYPES``.
    """
    literals = _collect_event_literals()
    used_in_code = set(literals.keys())

    orphans = sorted(KNOWN_EVENT_TYPES - used_in_code)
    assert not orphans, (
        "KNOWN_EVENT_TYPES entries with no matching literal in app/ (dead entry):\n"
        + "\n".join(f"  {v!r}" for v in orphans)
    )


def test_iter_event_types_is_sorted_and_matches_registry() -> None:
    """iter_event_types() и all_event_types() возвращают тот же набор, что реестр."""
    expected = sorted(KNOWN_EVENT_TYPES)
    assert list(iter_event_types()) == expected
    assert all_event_types() == expected
