"""Парсер ERP-выгрузки (отчёт 1С «Справочник: Сотрудники»).

Поддерживаемые форматы (по расширению + содержимому):

* ``txt`` / ``csv`` — таб-/запятая-/точка-с-запятой-separated, авто-кодировка
  (BOM → charset_normalizer → cp1251 fallback). Один из приложенных заказчиком
  файлов был cp1251 — хардкод utf-8 сломался бы молча.
* ``xlsx`` — через ``openpyxl`` (уже в deps).
* ``xls`` (legacy OLE2, Excel 97-2003) — через ``xlrd==2.0.1``.

Ожидаемая структура: колонки **ФИО**, **дата рождения** (``ДД.ММ.ГГГГ``),
**пол** (``Мужской``/``Женский``). Заголовок-«Параметры:» и служебные строки
фильтруются автоматически (по непарсимости даты во 2-й колонке).

Обработка дублей (ERP выгружает одного человека N раз — несколько должностей):

* **ФИО + дата + пол полностью совпадают** → дедуплицируем, берём 1 запись
  (это норма, данные идентичны).
* **ФИО совпадает, но дата ИЛИ пол различаются** → возможный однофамильца или
  ошибка выгрузки. **Не пишем ничего**, попадает в ``conflicts`` для ручного
  разбора админом (docs/wip/erp-sync.md, решение от 2026-07-31).

Чистые парные функции — тестируются без БД/Redis.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

# Согласовано с users.gender CHECK (миграция 087) и схемой.
GenderValue = Literal["male", "female"]

# Форматы вложений, которые мы умеем парсить.
Format = Literal["txt", "csv", "xlsx", "xls"]

SUPPORTED_FORMATS: tuple[str, ...] = ("txt", "csv", "xlsx", "xls")

# 1С «Мужской»/«Женский». Регистр/пробелы не важны. Дополнять по мереNeed.
_MALE_TOKENS = {"мужской", "м", "male", "муж"}
_FEMALE_TOKENS = {"женский", "ж", "female", "жен"}

# «25.08.1974» — строгий формат ДД.ММ.ГГГГ (точка-разделитель, как в выгрузке 1С).
_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")

# ФИО с примечанием в скобках: «Зубайрова Н.А. (Сухорукова с 01.09.2021)».
# Скобки ломают точный матч — обрезаем по первой «(».
_FIO_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


@dataclass
class ParsedRow:
    """Одна распознанная строка выгрузки (после нормализации)."""

    fio: str  # исходное ФИО (с заглавных, как в файле) — для отчёта/матчинга
    fio_normalized: str  # lower + ё→е + обрезка скобок — ключ дедупа
    birth_date: date
    gender: GenderValue


@dataclass
class ParseError:
    """Нераспознанная строка + причина (для раздела отчёта «Ошибки»)."""

    raw: str  # первые ~200 символов строки
    reason: str


@dataclass
class ParsedFile:
    """Результат парсинга всего вложения.

    ``rows`` — дедуплицированные валидные записи (ключевые для матчинга).
    ``conflicts`` — ФИО с разными датами/полом (НЕ пишем, в отчёт админу).
    ``errors`` — строки, которые не удалось распознать.
    """

    rows: list[ParsedRow] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)

    @property
    def total_raw(self) -> int:
        """Сумма всех распознанных случаев (для rows_total в отчёте)."""
        return len(self.rows) + len(self.conflicts) + len(self.errors)


# ── Детект формата ────────────────────────────────────────────────────────────


def detect_format(filename: str) -> Format | None:
    """Определить формат по расширению имени файла.

    Возвращает ``None`` для неподдерживаемых расширений (HTML, PDF и т.д.) —
    вызывающий код показывает ошибку «переотправьте в TXT/XLSX».
    """
    name = filename.lower().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".tsv") or name.endswith(".txt"):
        return "txt"
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return "xlsx"
    if name.endswith(".xls"):
        return "xls"
    return None


# ── Нормализация полей ────────────────────────────────────────────────────────


def normalize_fio(raw: str) -> tuple[str, str]:
    """Нормализация ФИО для матчинга.

    Возвращает кортеж ``(display, normalized)``:

    * ``display`` — исходное ФИО (обрезаны скобки-примечания и лишние пробелы),
      сохраняет регистр — пойдёт в отчёт админу и в matcher (CI внутри).
    * ``normalized`` — lower + ё→е, ключ дедупа.

    Обрезка скобок: «Зубайрова Н.А. (Сухорукова с 01.09.2021)» →
    «Зубайрова Н.А.». Без этого точный матч ломается.
    """
    s = _FIO_PAREN_RE.sub("", raw).strip()
    while "  " in s:  # схлопнуть двойные пробелы
        s = s.replace("  ", " ")
    normalized = s.lower().replace("ё", "е").strip()
    return s, normalized


def parse_birth_date(raw: str) -> date | None:
    """Парсинг даты строго в формате ``ДД.ММ.ГГГГ`` (1С).

    Возвращает ``None`` для невалидных/нестроковых значений — вызывающий код
    относит строку в ``errors``.
    """
    if not isinstance(raw, str):
        return None
    m = _DATE_RE.match(raw)
    if not m:
        return None
    try:
        d, mo, y = (int(g) for g in m.groups())
        return date(y, mo, d)
    except ValueError:
        return None


def parse_gender(raw: str) -> GenderValue | None:
    """Парсинг пола: «Мужской»/«Женский» → ``'male'``/``'female'``.

    Толерантен к регистру, пробелам и сокращениям (М/Ж). ``None`` = не распознан.
    """
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().rstrip(".")
    if token in _MALE_TOKENS:
        return "male"
    if token in _FEMALE_TOKENS:
        return "female"
    return None


def _looks_like_header(raw_date_col: str, raw_gender_col: str) -> bool:
    """Похоже ли строка на заголовок колонок (а не на данные).

    Типовая выгрузка 1С начинается заголовком:
    ``Сотрудник | Физическое лицо.Дата рождения | Физическое лицо.Пол``
    Без распознавания заголовок попадал бы в errors (дата/пол не парсятся),
    засоряя каждый импорт одной лишней «ошибкой».

    Признаки (оба, AND — чтобы не было ложных срабатываний на данных вроде
    «не-дата» или «Непонятно»):

    * 2-я колонка содержит «дата рождения» (типовой заголовок 1С) — простого
      «дата» недостаточно: реальное значение «не-дата» тоже содержит эту
      подстроку и не должно маскироваться под заголовок.
    * 3-я колонка оканчивается на «пол» (с учётом префикса «Физическое лицо.»
      из 1С) — но не просто содержит «пол» внутри слова (напр. «Непонятно»).
    """
    d = (raw_date_col or "").strip().lower()
    g = (raw_gender_col or "").strip().lower()
    return "дата рождения" in d and g.endswith("пол")


# ── Декодирование текста ─────────────────────────────────────────────────────


def _decode_text(data: bytes) -> str:
    """Декодировать bytes в str с авто-определением кодировки.

    Порядок: BOM-маркер → ``charset_normalizer`` (если установлен) → cp1251
    fallback. Один из приложенных файлов был cp1251 (Windows-1251), и хардкод
    utf-8 сломался бы молча (кракозябры → все строки в errors).
    """
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        # UTF-16 LE/BE с BOM
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Fallback: попытка определить кодировку.
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(data).best()
        if result is not None:
            return str(result)
    except Exception:
        pass
    # Последний рубеж: cp1251 (типично для 1С-выгрузок на Windows).
    return data.decode("cp1251", errors="replace")


def _detect_delimiter(sample: str) -> str:
    """Угадать разделитель (tab / ; / ,) по первой непустой строке-данным.

    1С чаще всего использует tab; ручной экспорт в CSV — `,` или `;`.
    """
    for line in sample.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "\t" in line:
            return "\t"
        if ";" in line:
            return ";"
        if "," in line:
            return ","
        return "\t"  # один столбец — всё равно tab, парсер вернёт ошибку формата
    return "\t"


# ── Основной entry-point ─────────────────────────────────────────────────────


def parse_attachment(*, filename: str, data: bytes) -> ParsedFile:
    """Распарсить вложение ERP-выгрузки.

    Args:
        filename: имя файла вложения (для определения формата по расширению).
        data: сырые байты содержимого.

    Returns:
        :class:`ParsedFile` с дедуплицированными ``rows``, ``conflicts`` и
        ``errors``. Никогда не бросает исключение — всё невалидное попадает в
        ``errors``, чтобы один битый файл не ронял весь импорт.
    """
    fmt = detect_format(filename)
    if fmt is None:
        return ParsedFile(
            errors=[
                ParseError(
                    raw=filename[:200],
                    reason=(
                        f"Неподдерживаемый формат файла. Допустимо: {', '.join(SUPPORTED_FORMATS)}."
                    ),
                )
            ]
        )

    try:
        raw_records = _extract_records(fmt, data)
    except Exception as exc:
        logger.warning("erp_sync.parser.extract_failed", filename=filename, error=str(exc))
        return ParsedFile(
            errors=[ParseError(raw=filename[:200], reason=f"Ошибка чтения файла: {exc}")]
        )

    return _normalize_and_dedup(raw_records)


def _extract_records(fmt: Format, data: bytes) -> list[list[str]]:
    """Извлечь «сырые» строковые записи (по 3 колонки) из файла любого формата.

    Возвращает список списков ячеек (как есть, без валидации). Служебные строки
    (заголовок «Параметры:», пустые) отсеиваются позже в ``_normalize_and_dedup``.
    """
    if fmt in ("txt", "csv"):
        text = _decode_text(data)
        delim = _detect_delimiter(text)
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        return [row for row in reader if any((c or "").strip() for c in row)]
    if fmt == "xlsx":
        return _extract_xlsx(data)
    if fmt == "xls":
        return _extract_xls(data)
    # fmt гарантирует Literal, но для mypy — явный unreachable.
    raise ValueError(f"Unsupported format: {fmt}")


def _extract_xlsx(data: bytes) -> list[list[str]]:
    """Извлечь записи из .xlsx через openpyxl (режим read-only, без формул)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    records: list[list[str]] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any((c or "").strip() for c in cells):
                records.append(cells)
    wb.close()
    return records


def _extract_xls(data: bytes) -> list[list[str]]:
    """Извлечь записи из legacy .xls (OLE2) через xlrd 2.0.1."""
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    records: list[list[str]] = []
    for sheet in book.sheets():
        for r in range(sheet.nrows):
            cells = ["" if c == "" else str(c) for c in sheet.row_values(r)]
            if any((c or "").strip() for c in cells):
                records.append(cells)
    book.release_resources()
    return records


def _normalize_and_dedup(records: list[list[str]]) -> ParsedFile:
    """Валидация строк + дедуп дублей + детект конфликтов.

    Алгоритм:

    1. Каждая запись → ``(fio, birth_date, gender)``. Невалидные (нет ФИО,
       дата не парсится, пол не распознан) → ``errors`` с указанием причины.
    2. Группировка по ``fio_normalized``:

       * один вариант (одно значение в группе) → ``rows``;
       * несколько вариантов с **полностью идентичными** ``(date, gender)`` →
         дедуп (1 запись в ``rows``);
       * несколько вариантов с **разными** ``(date, gender)`` → ``conflicts``
         (НЕ пишем, для ручного разбора).
    """
    by_fio: dict[str, list[ParsedRow]] = {}
    errors: list[ParseError] = []

    for cells in records:
        # Нужны минимум 3 колонки: ФИО, дата, пол. Лишние — игнорируем.
        if len(cells) < 3:
            # Пропускаем «шум»: пустые строки, заголовок-«Параметры:» из 1С,
            # который часто в первых колонках. Если данных мало — в errors
            # только если строка выглядит осмысленно (содержит дату).
            joined = " ".join(cells).strip()
            if joined and parse_birth_date(joined.split()[-1] if joined.split() else ""):
                errors.append(ParseError(raw=joined[:200], reason="Меньше 3 колонок"))
            continue

        raw_fio, raw_date, raw_gender = cells[0], cells[1], cells[2]
        fio_display, fio_norm = normalize_fio(raw_fio)
        if not fio_norm:
            continue  # пустая строка ФИО — шум, пропускаем молча

        # Распознавание строки-заголовка колонок (типовая выгрузка 1С):
        # 2-я колонка содержит «дата»/«Дата рождения», 3-я — «пол». Без этой
        # проверки заголовок попадал бы в errors (дата/пол не парсятся),
        # засоряя каждый импорт одной «ошибкой».
        if _looks_like_header(raw_date, raw_gender):
            continue

        birth = parse_birth_date(raw_date)
        gender = parse_gender(raw_gender)

        # Валидация: дата и пол обязательны. Если хотя бы одно невалидно —
        # вся строка в errors (не partial-запись).
        reasons: list[str] = []
        if birth is None:
            reasons.append(f"дата не распознана («{raw_date}»)")
        if gender is None:
            reasons.append(f"пол не распознан («{raw_gender}»)")
        if reasons:
            errors.append(
                ParseError(
                    raw=f"{raw_fio} | {raw_date} | {raw_gender}".strip()[:200],
                    reason="; ".join(reasons),
                )
            )
            continue

        # После guards выше birth/gender гарантированно не None, но mypy не
        # сужает через накопление reasons-list. Уточняем тип явно.
        assert birth is not None and gender is not None  # type narrowing для mypy
        row = ParsedRow(fio=fio_display, fio_normalized=fio_norm, birth_date=birth, gender=gender)
        by_fio.setdefault(fio_norm, []).append(row)

    # Дедуп + детект конфликтов.
    rows: list[ParsedRow] = []
    conflicts: list[dict[str, Any]] = []
    for fio_norm, group in by_fio.items():
        # Уникальные варианты (date, gender) в группе.
        variants: dict[tuple[date, GenderValue], ParsedRow] = {}
        for r in group:
            variants.setdefault((r.birth_date, r.gender), r)
        if len(variants) == 1:
            # Все строки группы идентичны → 1 запись (норма, дедуп).
            rows.append(next(iter(variants.values())))
        else:
            # Разные дата/пол при том же ФИО → конфликт (однофамильца?).
            # Берём display из первой строки группы для отчёта.
            conflicts.append(
                {
                    "fio": group[0].fio,
                    "fio_normalized": fio_norm,
                    "occurrences": len(group),
                    "variants": [
                        {"birth_date": v.birth_date.isoformat(), "gender": v.gender}
                        for v in variants.values()
                    ],
                }
            )

    logger.info(
        "erp_sync.parser.done",
        rows=len(rows),
        conflicts=len(conflicts),
        errors=len(errors),
    )
    return ParsedFile(rows=rows, conflicts=conflicts, errors=errors)
