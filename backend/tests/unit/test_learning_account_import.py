from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from app.api.learning import admin_routes
from app.services.learning import account_import


def _workbook(rows: list[tuple[object, ...]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


class TestParseLearningAccountsXlsx:
    def test_template_roundtrip(self):
        parsed = account_import.parse_xlsx(account_import.build_template())

        assert parsed.errors == []
        assert len(parsed.rows) == 1
        assert parsed.rows[0].account.email == "ivanov@example.ru"
        assert parsed.rows[0].account.full_name == "Иванов Иван"

    def test_aliases_optional_columns_and_invalid_rows(self):
        data = _workbook(
            [
                ("Имя Фамилия", "E-mail", "Department", "Job title"),
                ("  Пётр Петров  ", " PETROV@EXAMPLE.RU ", " ИТ ", " Инженер "),
                ("Без Адреса", "not-an-email", None, None),
                (None, None, None, None),
            ]
        )

        parsed = account_import.parse_xlsx(data)

        assert len(parsed.rows) == 1
        assert parsed.rows[0].row_number == 2
        assert parsed.rows[0].account.email == "petrov@example.ru"
        assert parsed.rows[0].account.department == "ИТ"
        assert len(parsed.errors) == 1
        assert parsed.errors[0].row_number == 3
        assert "email" in parsed.errors[0].message

    def test_excel_values_are_coerced_to_strings_before_validation(self):
        parsed = account_import.parse_xlsx(_workbook([("ФИО", "email"), (12345, 67890)]))

        assert parsed.rows == []
        assert len(parsed.errors) == 1
        assert "email" in parsed.errors[0].message

    @pytest.mark.parametrize(
        "data,message",
        [
            (b"not a workbook", "корректным xlsx"),
            (_workbook([]), "Файл пуст"),
            (_workbook([("Имя", "Отдел")]), "обязательные колонки"),
        ],
        ids=["not-xlsx", "empty-workbook", "missing-required-columns"],
    )
    def test_rejects_invalid_workbook_contract(self, data: bytes, message: str):
        with pytest.raises(account_import.ImportFormatError, match=message):
            account_import.parse_xlsx(data)

    def test_rejects_more_than_1000_non_empty_rows(self):
        rows: list[tuple[object, ...]] = [("ФИО", "email")]
        rows.extend((f"Участник {index}", f"user{index}@example.ru") for index in range(1001))

        with pytest.raises(account_import.ImportFormatError, match="не более 1000"):
            account_import.parse_xlsx(_workbook(rows))

    def test_rejects_duplicate_semantic_headers(self):
        data = _workbook([("ФИО", "Имя Фамилия", "email")])

        with pytest.raises(account_import.ImportFormatError, match="повторно"):
            account_import.parse_xlsx(data)

    def test_rejects_excessive_uncompressed_archive(self, monkeypatch):
        monkeypatch.setattr(account_import, "MAX_UNCOMPRESSED_BYTES", 10)

        with pytest.raises(account_import.ImportFormatError, match="Распакованный xlsx"):
            account_import.parse_xlsx(account_import.build_template())


class TestLearningAccountImportEndpoints:
    @pytest.mark.asyncio
    async def test_template_response_is_downloadable_xlsx(self):
        response = await admin_routes.download_import_template(None)  # type: ignore[arg-type]

        assert response.media_type == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response.headers["content-disposition"] == (
            'attachment; filename="learning-accounts-template.xlsx"'
        )
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert account_import.parse_xlsx(bytes(response.body)).errors == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("filename", "data", "expected_status"),
        [
            ("accounts.csv", b"email,name", 400),
            ("accounts.xlsx", b"", 400),
            ("accounts.xlsx", b"not a workbook", 422),
            (
                "accounts.xlsx",
                b"x" * (account_import.MAX_IMPORT_BYTES + 1),
                413,
            ),
        ],
        ids=["wrong-extension", "empty", "corrupt", "too-large"],
    )
    async def test_import_rejects_invalid_uploads(
        self,
        filename: str,
        data: bytes,
        expected_status: int,
    ):
        upload = UploadFile(filename=filename, file=io.BytesIO(data))

        with pytest.raises(HTTPException) as exc_info:
            await admin_routes.import_accounts(
                upload,
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
            )

        assert exc_info.value.status_code == expected_status
