"""Unit-тесты отчёта импорта отсутствий (services/erp_sync/absences_report.py).

Покрытие:

* тема письма (успех / с проблемами / failed / skipped)
* структура HTML/plain-тел (разделы появляются только когда непустые)
* XSS-эскейп (ФИО с <script>, position с HTML)
* форматирование периода (обычный / однодневный / ISO→RU)
* человекочитаемые названия kinds
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")

from app.models.erp_sync import ErpAbsencesRun
from app.services.erp_sync.absences_report import (
    build_absences_report_bodies,
    build_absences_subject,
)


def _make_run(**overrides: object) -> ErpAbsencesRun:
    """Собрать ErpAbsencesRun с дефолтами для тестов отчёта."""
    defaults: dict[str, object] = dict(
        id=1,
        message_id=None,
        attachment_name="absences.txt",
        triggered_by="cron",
        started_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 4, 12, 1, tzinfo=UTC),
        status="success",
        rows_total=10,
        rows_matched=8,
        rows_inserted=8,
        rows_unmatched=2,
        rows_ambiguous=0,
        errors=0,
        report={},
    )
    defaults.update(overrides)
    return ErpAbsencesRun(**defaults)


class TestBuildSubject:
    def test_success_no_problems(self):
        run = _make_run(rows_unmatched=0, rows_ambiguous=0, errors=0, status="success")
        assert "завершён" in build_absences_subject(run)
        assert "8 добавлено" in build_absences_subject(run)

    def test_with_problems(self):
        run = _make_run(rows_unmatched=2, errors=1, status="partial")
        subj = build_absences_subject(run)
        assert "3 требуют внимания" in subj

    def test_failed_prefix(self):
        run = _make_run(status="failed", rows_inserted=0, errors=5)
        assert build_absences_subject(run).startswith("ОШИБКА:")

    def test_skipped_prefix(self):
        run = _make_run(status="skipped", rows_inserted=0, rows_total=0)
        assert "пропуск:" in build_absences_subject(run)


class TestBuildBodies:
    def test_html_and_plain_returned(self):
        run = _make_run(report={})
        html_body, plain_body = build_absences_report_bodies(run)
        assert isinstance(html_body, str)
        assert isinstance(plain_body, str)
        assert "ERP-отсутствия сотрудников" in plain_body
        assert "font-family:Arial" in html_body

    def test_summary_present(self):
        run = _make_run()
        html_body, plain_body = build_absences_report_bodies(run)
        assert "Всего строк в файле" in html_body
        assert "Всего: 10" in plain_body
        assert "добавлено: 8" in plain_body

    def test_inserted_section_shown(self):
        run = _make_run(
            report={
                "inserted": [
                    {
                        "fio": "Иванов Иван",
                        "user_id": "u1",
                        "kind": "vacation_main",
                        "position": "Инженер",
                        "department": "Отдел",
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-20",
                    }
                ]
            }
        )
        html_body, plain_body = build_absences_report_bodies(run)
        assert "Иванов Иван" in html_body
        assert "Отпуск основной" in html_body
        assert "10.08.2026 – 20.08.2026" in html_body
        assert "Иванов Иван (Отпуск основной, 10.08.2026 – 20.08.2026)" in plain_body

    def test_single_day_period_format(self):
        run = _make_run(
            report={
                "inserted": [
                    {
                        "fio": "Петров Пётр",
                        "user_id": "u2",
                        "kind": "day_off_paid",
                        "position": None,
                        "department": None,
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-10",
                    }
                ]
            }
        )
        html_body, _plain_body = build_absences_report_bodies(run)
        # Однодневный отгул — период без диапазона.
        assert "10.08.2026 – 10.08.2026" not in html_body
        assert "10.08.2026" in html_body

    def test_empty_sections_omitted(self):
        run = _make_run(report={"inserted": [], "unmatched": [], "ambiguous": [], "errors": []})
        html_body, _plain_body = build_absences_report_bodies(run)
        assert "Добавлено (" not in html_body
        assert "Не сопоставлено (" not in html_body
        assert "Неоднозначно (" not in html_body
        assert "Ошибки парсинга (" not in html_body

    def test_xss_escape_in_fio(self):
        run = _make_run(
            report={
                "inserted": [
                    {
                        "fio": "<script>alert(1)</script>",
                        "user_id": "u3",
                        "kind": "sick",
                        "position": None,
                        "department": None,
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-12",
                    }
                ]
            }
        )
        html_body, _ = build_absences_report_bodies(run)
        assert "<script>" not in html_body  # эскейпнуто
        assert "&lt;script&gt;" in html_body

    def test_xss_escape_in_position(self):
        run = _make_run(
            report={
                "inserted": [
                    {
                        "fio": "Иванов",
                        "user_id": "u4",
                        "kind": "business_trip",
                        "position": "<img src=x onerror=alert(1)>",
                        "department": "Отдел",
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-12",
                    }
                ]
            }
        )
        html_body, _ = build_absences_report_bodies(run)
        assert "<img" not in html_body
        assert "&lt;img" in html_body

    def test_xss_escape_in_errors(self):
        run = _make_run(
            errors=1,
            report={"errors": [{"raw": "<script>x</script> | мусор", "reason": "не распознано"}]},
        )
        html_body, _ = build_absences_report_bodies(run)
        assert "<script>x</script>" not in html_body

    def test_all_kinds_have_labels(self):
        # Все 7 canonical kinds должны иметь человекочитаемое название в отчёте.
        for kind, _label in [
            ("vacation_main", "Отпуск основной"),
            ("vacation_extra", "Дополнительный отпуск"),
            ("unpaid_leave", "Отпуск неоплачиваемый"),
            ("sick", "Болезнь"),
            ("business_trip", "Командировка"),
            ("day_off_paid", "оплачиваемые"),
            ("day_off_unpaid", "неоплачиваемые"),
        ]:
            run = _make_run(
                report={
                    "inserted": [
                        {
                            "fio": "Тест",
                            "user_id": "u",
                            "kind": kind,
                            "position": None,
                            "department": None,
                            "start_date": "2026-08-10",
                            "end_date": "2026-08-11",
                        }
                    ]
                }
            )
            html_body, plain_body = build_absences_report_bodies(run)
            assert _label in html_body, f"kind {kind} без человекочитаемой метки"
            assert _label in plain_body

    def test_triggered_by_label(self):
        run_cron = _make_run(triggered_by="cron")
        run_manual = _make_run(triggered_by="manual")
        assert "автоматически" in build_absences_report_bodies(run_cron)[0]
        assert "вручную" in build_absences_report_bodies(run_manual)[0]
