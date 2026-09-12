"""XLSX-импорт вопросов теста (этап 2; ТЗ §13, §15 — Aiken-подобный формат).

Правило «каждый импорт — со скачиваемым шаблоном» (§13): колонки описаны
в одном месте этого модуля — ``build_template`` и ``parse_xlsx`` читают
одну и ту же спецификацию, расхождение исключено.

Формат: одна строка = один вопрос.
``Вопрос | Вариант A | Вариант B | Вариант C | Вариант D | Верный | Несколько ответов``
«Верный» — буквы вариантов через запятую (``A`` или ``A, C``);
«Несколько ответов» — да/нет (пусто = нет); для single верным обязан быть
ровно один вариант, для multi — хотя бы один.
"""

from __future__ import annotations

import io
import string
from dataclasses import dataclass
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError as PydanticValidationError

from app.schemas.learning import ImportedQuestionIn, OptionIn

MAX_IMPORT_QUESTIONS = 200
# Защита от zip-бомб — та же, что у импорта учёток (прецедент account_import).
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 500

QUESTION_TEMPLATE_FILENAME = "learning-questions-template.xlsx"

_OPTION_LETTERS = string.ascii_uppercase[:4]  # A–D, как в шаблоне ТЗ

_QUESTION_HEADERS = (
    "Вопрос",
    "Вариант A",
    "Вариант B",
    "Вариант C",
    "Вариант D",
    "Верный",
    "Несколько ответов",
)
_HINT_ROW = (
    "Текст вопроса",
    "Первый вариант ответа",
    "Второй вариант",
    "Третий вариант (можно оставить пустым)",
    "Четвёртый вариант (можно оставить пустым)",
    "Буквы верных вариантов: A или A, C",
    "да / нет (пусто = нет)",
)
_HEADER_KEYS: tuple[tuple[str, str], ...] = (
    ("text", "вопрос"),
    ("option_a", "вариант a"),
    ("option_b", "вариант b"),
    ("option_c", "вариант c"),
    ("option_d", "вариант d"),
    ("correct", "верный"),
    ("multi", "несколько ответов"),
)
# Колонки, без которых шаблон не распознаётся (C/D/multi — опциональны).
_REQUIRED_HEADER_KEYS = frozenset({"text", "option_a", "option_b", "correct"})

_YES_VALUES = {"да", "yes", "true", "истина", "1", "+"}
_NO_VALUES = {"нет", "no", "false", "ложь", "0", "-", "", "single"}


class ImportFormatError(ValueError):
    """Файл целиком не может быть разобран как допустимый шаблон."""


@dataclass(frozen=True, slots=True)
class ParsedQuestion:
    row_number: int
    question: ImportedQuestionIn


@dataclass(frozen=True, slots=True)
class ParsedRowError:
    row_number: int
    message: str


@dataclass(frozen=True, slots=True)
class ParsedQuestions:
    questions: list[ParsedQuestion]
    errors: list[ParsedRowError]


def _cell_text(value: object) -> str:
    """Ячейка как строка (Excel любит превращать текст в числа/даты)."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_multi(raw: str) -> bool:
    lowered = raw.lower()
    if lowered in _YES_VALUES:
        return True
    if lowered in _NO_VALUES:
        return False
    raise ValueError(f"«Несколько ответов»: ожидается «да» или «нет», получено «{raw}»")


def _parse_correct(raw: str, option_raws: list[str]) -> set[int]:
    if not raw:
        raise ValueError("Не указаны буквы верных вариантов (колонка «Верный»)")
    indexes: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        letter = chunk.strip().upper()
        if not letter:
            continue
        if len(letter) != 1 or letter not in _OPTION_LETTERS:
            raise ValueError(f"Некорректная буква варианта: «{letter}» (допустимо A–D)")
        idx = _OPTION_LETTERS.index(letter)
        if idx >= len(option_raws) or not option_raws[idx]:
            raise ValueError(f"Верный вариант «{letter}» не заполнен в строке")
        indexes.add(idx)
    if not indexes:
        raise ValueError("Не указаны буквы верных вариантов (колонка «Верный»)")
    return indexes


def _build_question(values: tuple[object, ...], columns: dict[str, int]) -> ImportedQuestionIn:
    def cell(key: str) -> str:
        idx = columns[key]
        return _cell_text(values[idx]) if idx < len(values) else ""

    text = cell("text")
    option_raws = [cell(f"option_{letter.lower()}") for letter in _OPTION_LETTERS]

    if not text:
        raise ValueError("Пустой текст вопроса")
    option_texts = [raw for raw in option_raws if raw]
    if len(option_texts) < 2:
        raise ValueError("Нужно минимум два варианта ответа")

    multi = _parse_multi(cell("multi").lower())
    correct_indexes = _parse_correct(cell("correct"), option_raws)
    if not multi and len(correct_indexes) != 1:
        raise ValueError("Для вопроса с одним ответом верный вариант должен быть ровно один")

    opts = [
        OptionIn(text=raw, is_correct=idx in correct_indexes)
        for idx, raw in enumerate(option_raws)
        if raw
    ]
    try:
        return ImportedQuestionIn(text=text, multi=multi, options=opts)
    except PydanticValidationError as exc:
        # Длинный текст и пр. — форматируем как обычную ошибку строки.
        raise ValueError(str(exc.errors()[0].get("msg", "некорректная строка"))) from exc


def _header_map(values: tuple[object, ...]) -> dict[str, int]:
    """Буква колонки → индекс. Отсутствие обязательной колонки — ошибка файла."""
    normalized = {_cell_text(value).lower(): idx for idx, value in enumerate(values)}
    columns: dict[str, int] = {}
    missing: list[str] = []
    for key, header in _HEADER_KEYS:
        idx = normalized.get(header)
        if idx is None:
            if key in _REQUIRED_HEADER_KEYS:
                missing.append(header)
            idx = 10**6  # необязательная колонка отсутствует — «пусто»
        columns[key] = idx
    if missing:
        raise ImportFormatError(f"В шаблоне нет колонок: {', '.join(missing)}")
    return columns


def parse_xlsx(data: bytes) -> ParsedQuestions:
    """Разобрать первый лист; ошибочные строки вернуть в отчёте (не исключением)."""
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportFormatError("Файл больше 5 МБ")
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ImportFormatError("В xlsx слишком много внутренних файлов")
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ImportFormatError("Распакованный xlsx превышает лимит 50 МБ")
    except BadZipFile as exc:
        raise ImportFormatError("Файл не является корректным xlsx") from exc
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError) as exc:
        raise ImportFormatError("Файл не является корректным xlsx") from exc

    try:
        sheet = workbook.active
        if sheet is None:
            raise ImportFormatError("В файле нет листов")
        iterator = sheet.iter_rows(values_only=True)
        header_values: tuple[object, ...] | None = None
        for values in iterator:
            if any(_cell_text(value) for value in values):
                header_values = values
                break
        if header_values is None:
            raise ImportFormatError("Файл пуст")
        columns = _header_map(header_values)

        questions: list[ParsedQuestion] = []
        errors: list[ParsedRowError] = []
        for row_number, values in enumerate(iterator, start=2):
            if not any(_cell_text(value) for value in values):
                continue
            # Строка-подсказка из нашего шаблона (не данные, не ошибка).
            text_idx = columns["text"]
            if text_idx < len(values) and _cell_text(values[text_idx]) == _HINT_ROW[0]:
                continue
            if len(questions) + len(errors) >= MAX_IMPORT_QUESTIONS:
                raise ImportFormatError(
                    f"За один импорт допускается не более {MAX_IMPORT_QUESTIONS} вопросов"
                )
            try:
                question = _build_question(values, columns)
            except ValueError as exc:
                errors.append(ParsedRowError(row_number, str(exc)))
                continue
            questions.append(ParsedQuestion(row_number, question))
        return ParsedQuestions(questions=questions, errors=errors)
    finally:
        workbook.close()


def build_template() -> bytes:
    """Шаблон из той же спецификации колонок, по которой идёт разбор (§13)."""
    workbook = Workbook()

    fill = PatternFill("solid", fgColor="305496")
    widths = dict(zip("ABCDEFG", (46, 34, 34, 34, 34, 24, 20), strict=True))

    def _style_header(sheet: object, row_index: int) -> None:
        for cell in sheet[row_index]:  # type: ignore[index]
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center")

    sheet = workbook.active
    sheet.title = "Шаблон"
    sheet.append(_QUESTION_HEADERS)
    sheet.append(_HINT_ROW)
    _style_header(sheet, 1)
    for cell in sheet[2]:
        cell.font = Font(italic=True, color="808080")
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A3"

    example = workbook.create_sheet("Пример")
    example.append(_QUESTION_HEADERS)
    example.append(("Работы на высоте требуют наряд-допуска?", "Да", "Нет", "", "", "A", "нет"))
    example.append(
        (
            "Какие средства защиты обязательны?",
            "Каска",
            "Страховочная привязь",
            "Сменная обувь",
            "Наушники",
            "A, B",
            "да",
        )
    )
    _style_header(example, 1)
    for column, width in widths.items():
        example.column_dimensions[column].width = width

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
