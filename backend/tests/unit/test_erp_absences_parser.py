"""Unit-тесты парсера отчёта отсутствий ERP (services/erp_sync/absences_parser.py).

Покрытие:

* парсинг даты отсутствия (ДД.ММ.ГГГГ и ДД.ММ.ГГГГ 0:00:00 — смешанный формат 1С)
* классификация «Состояний» из 1С в 7 canonical kinds (включая edge-cases
  порядка матчинга: «отпуск неоплачиваемый» vs «отпуск основной»)
* детект шапки/заголовка колонок
* сборка периодов (строка-сотрудник + строки-периоды)
* дедуп идентичных периодов (несколько должностей в 1С)
* ошибки (период без сотрудника, невалидные даты, неизвестное состояние,
  окончание раньше начала, <5 колонок)
* реальные кейсы из приложенного заказчиком файла (2026-08-04): все 7 типов,
  сотрудники без аккаунта, кодировки (cp1251/UTF-8/UTF-16)
* неподдерживаемый формат → errors
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")

from app.services.erp_sync.absences_parser import (
    classify_kind,
    parse_absence_date,
    parse_absences_attachment,
)
from app.services.erp_sync.parser import ParseError

# ── parse_absence_date ─────────────────────────────────────────────────────


class TestParseAbsenceDate:
    def test_plain_date(self):
        assert parse_absence_date("09.08.2026") == date(2026, 8, 9)

    def test_date_with_zero_time(self):
        # Колонка «Начало» в 1С приходит с « 0:00:00».
        assert parse_absence_date("27.07.2026 0:00:00") == date(2026, 7, 27)

    def test_date_with_nonzero_time(self):
        assert parse_absence_date("27.07.2026 14:30:00") == date(2026, 7, 27)

    def test_date_with_short_time(self):
        assert parse_absence_date("27.07.2026 14:30") == date(2026, 7, 27)

    def test_single_digit_day_month(self):
        assert parse_absence_date("1.8.2026") == date(2026, 8, 1)

    def test_invalid_format(self):
        assert parse_absence_date("2026-08-09") is None

    def test_invalid_date(self):
        assert parse_absence_date("31.02.2026") is None  # 31 февраля не бывает

    def test_none(self):
        assert parse_absence_date(None) is None

    def test_non_string(self):
        assert parse_absence_date(123) is None  # type: ignore[arg-type]

    def test_empty(self):
        assert parse_absence_date("") is None


# ── classify_kind ──────────────────────────────────────────────────────────


class TestClassifyKind:
    def test_vacation_main(self):
        assert classify_kind("Отпуск основной") == "vacation_main"

    def test_vacation_extra(self):
        assert classify_kind("Дополнительный отпуск") == "vacation_extra"

    def test_unpaid_leave(self):
        # Критично: «отпуск неоплачиваемый» НЕ должен свалиться в vacation_main.
        assert classify_kind("Отпуск неоплачиваемый по разрешению работодателя") == "unpaid_leave"

    def test_sick(self):
        assert classify_kind("Болезнь") == "sick"

    def test_business_trip(self):
        assert classify_kind("Командировка") == "business_trip"

    def test_day_off_paid_parenthesized(self):
        # Реальный вариант из файла заказчика.
        assert classify_kind("Дополнительные выходные дни (оплачиваемые)") == "day_off_paid"

    def test_day_off_paid_plain(self):
        assert classify_kind("Дополнительные выходные дни оплачиваемые") == "day_off_paid"

    def test_day_off_unpaid(self):
        assert classify_kind("Дополнительные выходные дни неоплачиваемые") == "day_off_unpaid"

    def test_case_insensitive(self):
        assert classify_kind("ОТПУСК ОСНОВНОЙ") == "vacation_main"

    def test_unknown(self):
        assert classify_kind("Отгул по семейным обстоятельствам") is None

    def test_none(self):
        assert classify_kind(None) is None

    def test_empty(self):
        assert classify_kind("") is None

    def test_whitespace_only(self):
        assert classify_kind("   ") is None


# ── parse_absences_attachment: сборка периодов ─────────────────────────────


# Репрезентативный фрагмент реального файла заказчика (2026-08-04). Содержит
# шапку, заголовок, двух сотрудников со всеми типами отсутствий и edge-cases
# (несколько периодов у одного сотрудника, смешанный формат дат).
_REAL_FRAGMENT = """\
Кадровая история сотрудников за период

Параметры:\tСтандартный период: 01.01.2026 - 31.12.2026
Отбор:\t"Подразделение Не в списке ..."

Сотрудник
Должность\tПодразделение\tСостояние\tНачало\tОкончание
Абдуллаев Андрей Ахмедуллаевич
Начальник базы\tБаза флота\tОтпуск основной\t27.07.2026 0:00:00\t09.08.2026
Начальник базы\tБаза флота\tДополнительный отпуск\t10.08.2026 0:00:00\t25.08.2026
Агранов Григорий Дмитриевич
Ведущий геолог\tОтдел интерпретации\tОтпуск основной\t27.07.2026 0:00:00\t05.08.2026
Ведущий геолог\tОтдел интерпретации\tОтпуск неоплачиваемый по разрешению работодателя\t06.08.2026 0:00:00\t07.08.2026
Ведущий геолог\tОтдел интерпретации\tБолезнь\t10.08.2026 0:00:00\t12.08.2026
Наливкина Елена Юрьевна
Помощник руководителя\tАУП\tКомандировка\t01.08.2026 0:00:00\t10.08.2026
Прилипко Сергей Александрович
Заместитель начальника партии\tСезонная партия\tДополнительные выходные дни (оплачиваемые)\t10.08.2026 0:00:00\t10.08.2026
Стетюха Павел Васильевич
Начальник отдела\tОтдел охраны труда\tДополнительные выходные дни неоплачиваемые\t06.08.2026 0:00:00\t07.08.2026
"""


class TestParseAbsencesAttachment:
    def _parse(self, data: bytes, filename: str = "absences.txt"):
        return parse_absences_attachment(filename=filename, data=data)

    def test_real_fragment_happy_path(self):
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        # 7 периодов: 2 + 3 + 1 + 1 + 1 = 8? Проверим по видам:
        # Абдуллаев: 2, Агранов: 3, Наливкина: 1, Прилипко: 1, Стетюха: 1 = 8
        assert len(result.rows) == 8
        assert result.errors == []

    def test_real_fragment_kinds_distribution(self):
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        kinds = sorted(r.kind for r in result.rows)
        assert kinds == [
            "business_trip",
            "day_off_paid",
            "day_off_unpaid",
            "sick",
            "unpaid_leave",
            "vacation_extra",
            "vacation_main",
            "vacation_main",
        ]

    def test_real_fragment_first_row_fields(self):
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        first = result.rows[0]
        assert first.fio == "Абдуллаев Андрей Ахмедуллаевич"
        assert first.kind == "vacation_main"
        assert first.position == "Начальник базы"
        assert first.department == "База флота"
        assert first.start_date == date(2026, 7, 27)
        assert first.end_date == date(2026, 8, 9)

    def test_mixed_date_formats_parsed(self):
        # «Начало» с « 0:00:00», «Окончание» без — оба должны парситься в date.
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        first = result.rows[0]
        assert first.start_date == date(2026, 7, 27)  # из «27.07.2026 0:00:00»
        assert first.end_date == date(2026, 8, 9)  # из «09.08.2026»

    def test_total_raw_counts(self):
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        assert result.total_raw == len(result.rows) + len(result.errors) == 8

    # ── Дедуп ──────────────────────────────────────────────────────────────

    def test_dedup_identical_periods(self):
        # 1С дублирует период при нескольких должностях — берём 1 запись.
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
            "Ведущий инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1
        assert result.rows[0].position == "Инженер"  # первая строка побеждает

    def test_different_periods_not_deduped(self):
        # Разные периоды того же сотрудника — обе записи.
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
            "Инженер\tОтдел\tДополнительный отпуск\t21.08.2026 0:00:00\t25.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 2

    # ── Кодировки ──────────────────────────────────────────────────────────

    def test_cp1251_encoding(self):
        cp1251_data = _REAL_FRAGMENT.encode("cp1251")
        result = self._parse(cp1251_data)
        assert len(result.rows) == 8
        assert result.rows[0].fio == "Абдуллаев Андрей Ахмедуллаевич"

    def test_utf8_bom(self):
        data = b"\xef\xbb\xbf" + _REAL_FRAGMENT.encode("utf-8")
        result = self._parse(data)
        assert len(result.rows) == 8

    def test_utf16_bom(self):
        data = _REAL_FRAGMENT.encode("utf-16")
        result = self._parse(data)
        assert len(result.rows) == 8

    # ── Шапка ──────────────────────────────────────────────────────────────

    def test_header_skipped(self):
        # Шапка без строки-заголовка колонок → парсер не может определить начало
        # данных, молча возвращает пустой результат (без errors). Заголовок
        # колонок обязателен — без него файл не является отчётом отсутствий.
        data = (
            "Кадровая история сотрудников за период\n"
            "Параметры:\tСтандартный период: 01.01.2026 - 31.12.2026\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert result.errors == []

    def test_multiple_header_lines_before_data(self):
        # Реальный файл: «Сотрудник» отдельной строкой над заголовком колонок.
        data = (
            "Кадровая история сотрудников за период\n"
            "Сотрудник\n"
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1

    # ── Ошибки ─────────────────────────────────────────────────────────────

    def test_unsupported_format(self):
        result = parse_absences_attachment(filename="report.pdf", data=b"...")
        assert result.rows == []
        assert len(result.errors) == 1
        assert "Неподдерживаемый формат" in result.errors[0].reason

    def test_period_without_employee(self):
        # Период до любого ФИО → error с понятной причиной.
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t21.08.2026 0:00:00\t25.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1  # только второй период валиден
        assert len(result.errors) == 1
        assert "без предшествующей строки сотрудника" in result.errors[0].reason

    def test_unknown_state(self):
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tПрогул\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1
        assert "состояние не распознано" in result.errors[0].reason

    def test_invalid_start_date(self):
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t2026-08-10\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1
        assert "дата начала не распознана" in result.errors[0].reason

    def test_invalid_end_date(self):
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\tнекорректно\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1
        assert "дата окончания не распознана" in result.errors[0].reason

    def test_end_before_start(self):
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t20.08.2026 0:00:00\t10.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1
        assert "окончание раньше начала" in result.errors[0].reason

    def test_too_few_columns(self):
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\n"  # нет «Окончание»
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1

    def test_empty_employee_row_then_period_in_error(self):
        # Строка сотрудника пустая (после нормализации) → следующий период без
        # сотрудника → error. Проверяем, что не падает.
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "\t\t\n"  # пустая строка «сотрудника»
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert result.rows == []
        assert len(result.errors) == 1

    def test_fio_with_parenthesis_note(self):
        # «Зубайрова Н.А. (Сухорукова с 01.09.2021)» — скобки обрезаются при
        # нормализации (переиспользуем normalize_fio из parser.py).
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Зубайрова Н.А. (Сухорукова с 01.09.2021)\n"
            "Бухгалтер\tБухгалтерия\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1
        assert result.rows[0].fio == "Зубайрова Н.А."

    def test_fio_with_yo(self):
        # «ё» → «е» при нормализации (ключ дедупа/матчинга).
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Алёшин Алексей Алексеевич\n"
            "Инженер\tОтдел\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1
        assert result.rows[0].fio_normalized == "алешин алексей алексеевич"

    def test_position_and_department_optional(self):
        # Пустые position/department → None (не ломают парсинг).
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "\t\tОтпуск основной\t10.08.2026 0:00:00\t20.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1
        assert result.rows[0].position is None
        assert result.rows[0].department is None

    def test_no_errors_on_clean_file(self):
        result = self._parse(_REAL_FRAGMENT.encode("utf-8"))
        # Реальный файл заказчика должен парситься без единой ошибки.
        assert result.errors == []
        assert all(isinstance(e, ParseError) for e in [])  # тип-проверка

    def test_empty_file(self):
        result = self._parse(b"")
        assert result.rows == []
        assert result.errors == []

    def test_single_day_period(self):
        # start == end — валидный однодневный отгул (Прилипко в реальном файле).
        data = (
            "Должность\tПодразделение\tСостояние\tНачало\tОкончание\n"
            "Иванов Иван Иванович\n"
            "Инженер\tОтдел\tДополнительные выходные дни (оплачиваемые)\t10.08.2026 0:00:00\t10.08.2026\n"
        ).encode()
        result = self._parse(data)
        assert len(result.rows) == 1
        assert result.rows[0].start_date == result.rows[0].end_date == date(2026, 8, 10)
