"""Общие утилиты парсинга для обоих потоков ERP-синхронизации.

Дни рождения (``parser``) и отсутствия (``absences_parser``) читают одинаковые
форматы файлов от 1С (txt/csv/xlsx/xls) с теми же ловушками кодировок и
разделителей. Чтобы не дублировать ~70 строк декодирования в двух модулях,
общие хелперы вынесены сюда.

Функции чистые (без БД/Redis) — тестируются независимо.
"""

from __future__ import annotations

import csv
import io
from typing import Literal


def decode_text(data: bytes) -> str:
    """Декодировать ``bytes`` в ``str`` с авто-определением кодировки.

    Порядок: BOM-маркер → ``charset_normalizer`` (если установлен) → cp1251
    fallback. Один из приложенных заказчиком файлов был cp1251 (Windows-1251),
    и хардкод utf-8 сломался бы молча (кракозябры → все строки в errors).
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


def detect_delimiter(sample: str) -> str:
    """Угадать разделитель (tab / ; / ,) по первой непустой строке-данным.

    1С чаще всего использует tab; ручной экспорт в CSV — ``,`` или ``;``.
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


def extract_text_records(data: bytes) -> list[list[str]]:
    """Извлечь записи из txt/csv/tsv-файла (декодирование + авто-разделитель).

    Возвращает список строк ячеек (без валидации). Пустые строки отфильтрованы.
    """
    text = decode_text(data)
    delim = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    return [row for row in reader if any((c or "").strip() for c in row)]


def extract_xlsx_records(data: bytes) -> list[list[str]]:
    """Извлечь записи из ``.xlsx`` через ``openpyxl`` (read-only, без формул)."""
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


def extract_xls_records(data: bytes) -> list[list[str]]:
    """Извлечь записи из legacy ``.xls`` (OLE2) через ``xlrd`` 2.0.1."""
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


# Тип переиспользуется парсерами, чтобы не дублировать Literal.
TextFormat = Literal["txt", "csv"]
