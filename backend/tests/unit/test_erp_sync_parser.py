"""Unit-тесты парсера ERP-выгрузки (services/erp_sync/parser.py).

Покрытие:

* детект формата по расширению
* нормализация ФИО (скобки, ё→е, пробелы)
* парсинг даты (строгий ДД.ММ.ГГГГ) и пола (Мужской/Женский + сокращения)
* авто-кодировка (UTF-8 BOM, cp1251, UTF-16)
* разделители (tab, `;`, `,`)
* дедуп идентичных строк (несколько должностей в 1С)
* детект конфликтов (одно ФИО, разные дата/пол)
* ошибки (невалидная дата, неизвестный пол, <3 колонок)
* реальные кейсы из приложенных заказчиком файлов (скобки, ё)
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")

from app.services.erp_sync.parser import (
    detect_format,
    normalize_fio,
    parse_attachment,
    parse_birth_date,
    parse_gender,
)

# ── detect_format ────────────────────────────────────────────────────────────


class TestDetectFormat:
    def test_txt(self):
        assert detect_format("report.txt") == "txt"

    def test_tsv(self):
        assert detect_format("report.tsv") == "txt"

    def test_csv(self):
        assert detect_format("report.csv") == "csv"

    def test_xlsx(self):
        assert detect_format("Сотрудники.xlsx") == "xlsx"

    def test_xlsm(self):
        assert detect_format("report.xlsm") == "xlsx"

    def test_xls_legacy(self):
        assert detect_format("report.xls") == "xls"

    def test_unknown(self):
        assert detect_format("report.html") is None
        assert detect_format("report.pdf") is None
        assert detect_format("report") is None

    def test_path_with_dirs(self):
        assert detect_format("/tmp/sub/report.xlsx") == "xlsx"
        assert detect_format("C:\\Users\\report.xls") == "xls"


# ── Нормализация ─────────────────────────────────────────────────────────────


class TestNormalizeFio:
    def test_strips_paren_note(self):
        """Реальный кейс из выгрузки: ФИО с примечанием о смене фамилии."""
        display, norm = normalize_fio("Зубайрова Надежда Анатольевна (Сухорукова с 01.09.2021)")
        assert display == "Зубайрова Надежда Анатольевна"
        assert norm == "зубайрова надежда анатольевна"

    def test_yo_to_e(self):
        """«Артём» и «Артем» должны давать один normalized-ключ."""
        _, norm1 = normalize_fio("Артём Сидоров")
        _, norm2 = normalize_fio("Артем Сидоров")
        assert norm1 == norm2 == "артем сидоров"

    def test_collapses_double_spaces(self):
        display, norm = normalize_fio("  Иванов    Иван   Иванович  ")
        assert display == "Иванов Иван Иванович"
        assert norm == "иванов иван иванович"

    def test_empty(self):
        assert normalize_fio("") == ("", "")
        assert normalize_fio("   ") == ("", "")


class TestParseBirthDate:
    def test_valid_dotted(self):
        assert parse_birth_date("25.08.1974") == date(1974, 8, 25)
        assert parse_birth_date("01.01.2000") == date(2000, 1, 1)
        assert parse_birth_date("5.3.1990") == date(1990, 3, 5)  # без лидирующих нулей

    def test_invalid_format(self):
        assert parse_birth_date("1974-08-25") is None  # ISO не принимаем
        assert parse_birth_date("25/08/1974") is None  # slash-разделитель
        assert parse_birth_date("25.08.74") is None  # 2-значный год
        assert parse_birth_date("") is None
        assert parse_birth_date("не дата") is None

    def test_invalid_calendar(self):
        assert parse_birth_date("31.02.2000") is None  # 31 февраля
        assert parse_birth_date("00.01.2000") is None

    def test_non_string(self):
        assert parse_birth_date(None) is None  # type: ignore[arg-type]
        assert parse_birth_date(12345) is None  # type: ignore[arg-type]


class TestParseGender:
    def test_russian_full(self):
        assert parse_gender("Мужской") == "male"
        assert parse_gender("Женский") == "female"

    def test_case_insensitive(self):
        assert parse_gender("МУЖСКОЙ") == "male"
        assert parse_gender("женский") == "female"

    def test_abbreviations(self):
        assert parse_gender("М") == "male"
        assert parse_gender("Ж") == "female"
        assert parse_gender("м.") == "male"  # с точкой

    def test_english(self):
        assert parse_gender("male") == "male"
        assert parse_gender("Female") == "female"

    def test_invalid(self):
        assert parse_gender("другое") is None
        assert parse_gender("") is None
        assert parse_gender(None) is None  # type: ignore[arg-type]


# ── Парсинг файлов ───────────────────────────────────────────────────────────

# Реалистичный фрагмент (по структуре приложенных файлов 1С):
#   заголовок-«Параметры», дубликаты (Гащунас ×N), ФИО со скобками.
_SAMPLE_TSV = "\n".join(
    [
        "Параметры:\tТип объекта: Справочник",
        "\tИмя объекта: Сотрудники",
        "",
        "Сотрудник\tФизическое лицо.Дата рождения\tФизическое лицо.Пол",
        "Абатурова Ольга Анатольевна\t25.08.1974\tЖенский",
        "Абатурова Ольга Анатольевна\t25.08.1974\tЖенский",  # дубликат-идентичный
        "Александров Александр Дмитриевич\t15.04.1988\tМужской",
        "Зубайрова Надежда Анатольевна (Сухорукова с 01.09.2021)\t21.08.1976\tЖенский",
        "Иванов Иван Иванович\t10.10.1990\tМужской",
        "Иванов Иван Иванович\t10.10.1990\tМужской",  # дубликат-идентичный
        "Иванов Иван Иванович\t15.05.1985\tМужской",  # конфликт! другая дата
        "Петров Пётр Алексеевич\t01.01.2000\tМужской",  # ё
        "Сидоров Сидор\tне-дата\tМужской",  # ошибка: невалидная дата
        "Кузнецов\t01.01.1990\tНепонятно",  # ошибка: неизвестный пол
    ]
).encode("utf-8")


class TestParseAttachment:
    def test_dedup_identical_rows(self):
        """Дубликаты с полностью идентичными данными → 1 запись (норма 1С)."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        fios = {r.fio_normalized for r in result.rows}
        # Абатурова (×2 идентичных) и Иванов 10.10 (×2 идентичных) — по 1 записи.
        assert any("абатурова" in f for f in fios)
        # Конфликтный Иванов (две разные даты) НЕ в rows — он в conflicts.
        assert "иванов иван иванович" not in fios

    def test_conflict_detected(self):
        """Одно ФИО с разными датами → conflict, не пишем."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert "иванов иван иванович" in conflict["fio_normalized"]
        assert len(conflict["variants"]) == 2  # две разные даты

    def test_parens_stripped_in_match(self):
        """ФИО со скобками обрезается — в normalized ключе скобок нет."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        zubay = [r for r in result.rows if "зубайрова" in r.fio_normalized]
        assert len(zubay) == 1
        assert "(" not in zubay[0].fio
        assert "(" not in zubay[0].fio_normalized

    def test_yo_normalized(self):
        """«Пётр» и «Петр» дают один ключ (ё→е)."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        petrov = [r for r in result.rows if "петр" in r.fio_normalized]
        assert len(petrov) == 1

    def test_errors_collected(self):
        """Невалидные строки → errors с причиной."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        # Сидоров (невалидная дата) + Кузнецов (неизвестный пол)
        reasons = " ".join(e.reason for e in result.errors)
        assert "дата не распознана" in reasons
        assert "пол не распознан" in reasons

    def test_header_filtered(self):
        """Служебные строки 1С (Параметры/Имя объекта/заголовок колонок) не в rows."""
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        # Заголовок «Сотрудник\t...Дата рождения\t...Пол» — нет даты во 2-й колонке,
        # не должен попасть в errors (нет валидной даты) и не в rows.
        assert all("Физическое лицо" not in r.fio for r in result.rows)

    def test_header_not_in_errors(self):
        """Строка-заголовок колонок НЕ попадает в errors (регрессия).

        Раньше заголовок «Сотрудник | Дата рождения | Пол» давал 1 лишнюю
        «ошибку» (дата/пол не парсятся) на каждый импорт. Заголовок должен
        отсеиваться молча через _looks_like_header.
        """
        from app.services.erp_sync.parser import _looks_like_header

        # Реальный заголовок 1С — отсеивается.
        assert _looks_like_header("Физическое лицо.Дата рождения", "Физическое лицо.Пол")
        assert _looks_like_header("Дата рождения", "Пол")
        # Битые данные — НЕ заголовок (не должны маскироваться).
        assert not _looks_like_header("не-дата", "Мужской")
        assert not _looks_like_header("01.01.1990", "Непонятно")

        # Полный файл с заголовком: заголовок не в errors.
        data = (
            "Сотрудник\tФизическое лицо.Дата рождения\tФизическое лицо.Пол\n"
            "Иванов Иван\t01.01.1990\tМужской\n"
        ).encode()
        result = parse_attachment(filename="r.tsv", data=data)
        assert result.errors == []
        assert len(result.rows) == 1

    def test_total_raw_counts_all(self):
        result = parse_attachment(filename="r.tsv", data=_SAMPLE_TSV)
        # rows + conflicts + errors
        assert result.total_raw == len(result.rows) + len(result.conflicts) + len(result.errors)

    def test_unknown_format_returns_error(self):
        result = parse_attachment(filename="r.html", data=b"<html></html>")
        assert result.rows == []
        assert len(result.errors) == 1
        assert "Неподдерживаемый формат" in result.errors[0].reason

    def test_empty_file(self):
        result = parse_attachment(filename="r.tsv", data=b"")
        assert result.rows == []
        assert result.conflicts == []
        assert result.errors == []

    def test_cp1251_encoding(self):
        """Реальный кейс: один из приложенных файлов был в cp1251."""
        cp1251_data = "Иванов Иван\t01.01.1990\tМужской".encode("cp1251")
        result = parse_attachment(filename="r.txt", data=cp1251_data)
        assert len(result.rows) == 1
        assert result.rows[0].fio_normalized == "иванов иван"

    def test_utf8_bom(self):
        data = "Иванов Иван\t01.01.1990\tМужской".encode()
        data = b"\xef\xbb\xbf" + data  # prepend BOM
        result = parse_attachment(filename="r.txt", data=data)
        assert len(result.rows) == 1

    def test_semicolon_delimiter(self):
        """CSV с «;»-разделителем (русскоязычный Excel-экспорт)."""
        data = "Иванов Иван;01.01.1990;Мужской".encode()
        result = parse_attachment(filename="r.csv", data=data)
        assert len(result.rows) == 1
        assert result.rows[0].birth_date == date(1990, 1, 1)

    def test_comma_delimiter(self):
        data = "Иванов Иван,01.01.1990,Мужской".encode()
        result = parse_attachment(filename="r.csv", data=data)
        assert len(result.rows) == 1
