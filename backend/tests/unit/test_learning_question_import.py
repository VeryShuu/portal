"""Unit-тесты xlsx-импорта вопросов (этап 2, §13/§15): спецификация колонок
едина для шаблона и парсера; ошибки строк — в отчёте, не исключения."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.services.learning import question_import as qi


def _xlsx(rows: list[tuple[object, ...]], header: tuple[object, ...] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(header or qi._QUESTION_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _template_bytes() -> bytes:
    return qi.build_template()


class TestTemplateRoundTrip:
    def test_template_parses_clean(self):
        """Нетронутый шаблон: строка-подсказка не ошибка, вопросов нет."""
        parsed = qi.parse_xlsx(_template_bytes())
        assert parsed.questions == []
        assert parsed.errors == []

    def test_template_is_xlsx(self):
        data = _template_bytes()
        assert data[:2] == b"PK"  # zip
        assert qi.QUESTION_TEMPLATE_FILENAME.endswith(".xlsx")

    def test_example_sheet_has_two_filled_questions(self):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(_template_bytes()))
        assert set(wb.sheetnames) >= {"Шаблон", "Пример"}
        ws = wb["Пример"]
        rows = list(ws.iter_rows(values_only=True))
        filled = [r for r in rows[1:] if r[0]]
        assert len(filled) == 2
        multi_row = next(r for r in filled if str(r[6]).lower() == "да")
        assert "A" in str(multi_row[5]) and "B" in str(multi_row[5])


class TestParseValid:
    def test_single_question(self):
        data = _xlsx([("Вопрос один?", "Да", "Нет", "", "", "A", "")])
        parsed = qi.parse_xlsx(data)
        assert len(parsed.questions) == 1
        q = parsed.questions[0].question
        assert q.text == "Вопрос один?"
        assert q.multi is False
        assert [(o.text, o.is_correct) for o in q.options] == [("Да", True), ("Нет", False)]

    def test_multi_question_letters_and_semicolon(self):
        data = _xlsx([("Выберите", "Каска", "Привязь", "Обувь", "Наушники", "a; b", "да")])
        parsed = qi.parse_xlsx(data)
        assert parsed.errors == []
        q = parsed.questions[0].question
        assert q.multi is True
        assert [o.is_correct for o in q.options] == [True, True, False, False]

    def test_optional_columns_absent_in_file(self):
        """Файл без колонок C/D/multi: single-вопросы разбираются, multi = нет."""
        data = _xlsx(
            [("Только два?", "Да", "Нет", "A", "")],
            header=("Вопрос", "Вариант A", "Вариант B", "Верный", "Несколько ответов"),
        )
        parsed = qi.parse_xlsx(data)
        assert parsed.errors == []
        assert parsed.questions[0].question.multi is False


class TestParseErrors:
    def test_single_with_two_correct(self):
        data = _xlsx([("Q?", "Да", "Возможно", "", "", "A, B", "нет")])
        parsed = qi.parse_xlsx(data)
        assert parsed.questions == []
        assert parsed.errors[0].message == (
            "Для вопроса с одним ответом верный вариант должен быть ровно один"
        )

    def test_correct_letter_points_to_empty_option(self):
        data = _xlsx([("Q?", "Да", "Нет", "", "", "D", "")])
        parsed = qi.parse_xlsx(data)
        assert "«D» не заполнен" in parsed.errors[0].message

    def test_unknown_letter(self):
        data = _xlsx([("Q?", "Да", "Нет", "", "", "E", "")])
        assert "A–D" in qi.parse_xlsx(data).errors[0].message

    def test_no_correct_marked(self):
        data = _xlsx([("Q?", "Да", "Нет", "", "", "", "")])
        assert "Не указаны буквы" in qi.parse_xlsx(data).errors[0].message

    def test_fewer_than_two_options(self):
        data = _xlsx([("Q?", "Только один", "", "", "", "A", "")])
        assert "минимум два варианта" in qi.parse_xlsx(data).errors[0].message

    def test_empty_question_text(self):
        data = _xlsx([("", "Да", "Нет", "", "", "A", "")])
        assert "Пустой текст вопроса" in qi.parse_xlsx(data).errors[0].message

    @pytest.mark.parametrize("raw", ["наверное", "2", "da net"])
    def test_garbage_multi_value(self, raw: str):
        data = _xlsx([("Q?", "Да", "Нет", "", "", "A", raw)])
        parsed = qi.parse_xlsx(data)
        assert parsed.errors and "«Несколько ответов»" in parsed.errors[0].message

    def test_missing_required_header(self):
        data = _xlsx(
            [("Q?", "Да", "A")],
            header=("Текст", "Ответ", "Верный"),
        )
        with pytest.raises(qi.ImportFormatError, match="нет колонок"):
            qi.parse_xlsx(data)

    def test_corrupt_file(self):
        with pytest.raises(qi.ImportFormatError):
            qi.parse_xlsx(b"this is not a zip archive")

    def test_empty_file_sheet(self):
        wb = Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        with pytest.raises(qi.ImportFormatError, match="пуст"):
            qi.parse_xlsx(buf.getvalue())

    def test_row_limit(self):
        rows = [(f"Вопрос {i}", "Да", "Нет", "", "", "A", "") for i in range(201)]
        with pytest.raises(qi.ImportFormatError, match="200"):
            qi.parse_xlsx(_xlsx(rows))


class TestTemplateHintSkipped:
    def test_hint_row_not_an_error(self):
        data = _xlsx(
            [
                qi._HINT_ROW,  # методист не удалил строку-подсказку
                ("Q?", "Да", "Нет", "", "", "A", ""),
            ]
        )
        parsed = qi.parse_xlsx(data)
        assert parsed.errors == []
        assert len(parsed.questions) == 1
