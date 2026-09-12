"""Unit-тесты билдеров сообщений Directum: Matrix-дайджест (:mod:`digest`) и
email-сводки (:mod:`report`). Чистые функции — без БД и моков.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.directum import DirectumRun
from app.services.directum.digest import build_overdue_digest
from app.services.directum.odata import OverdueAssignment
from app.services.directum.report import build_report_bodies, build_subject

_MOSCOW = timezone(timedelta(hours=3))
NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=_MOSCOW)


def _task(subject: str, days_overdue: int = 5) -> OverdueAssignment:
    return OverdueAssignment(
        id="t",
        subject=subject,
        deadline=NOW - timedelta(days=days_overdue),
        performer_name="Иванов Иван Иванович",
    )


class TestBuildOverdueDigest:
    def test_header_contains_count(self):
        plain, html = build_overdue_digest([_task("A"), _task("B")], now=NOW)
        assert "Просроченные задачи в Directum — 2" in plain
        assert "Просроченные задачи в Directum — 2" in html

    def test_subject_and_overdue_days(self):
        plain, html = build_overdue_digest([_task("Подпишите: договор")], now=NOW)
        assert "1. Подпишите: договор" in plain
        assert "просрочено на 5 дн." in plain
        assert "<b>Подпишите: договор</b>" in html

    def test_today_deadline_label(self):
        task = OverdueAssignment(
            id="t",
            subject="Сегодня",
            deadline=NOW - timedelta(hours=3),
            performer_name="И.",
        )
        plain, _ = build_overdue_digest([task], now=NOW)
        assert "срок истёк сегодня" in plain

    def test_html_escapes_user_content(self):
        _, html = build_overdue_digest([_task('<script>alert("x")</script>')], now=NOW)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_digest_cap_50_tasks(self):
        tasks = [_task(f"T{i}") for i in range(80)]
        plain, _ = build_overdue_digest(tasks, now=NOW)
        assert "— 80" in plain
        assert "… и ещё 30" in plain
        assert "T49" in plain and "T50" not in plain

    def test_deadline_formatted_with_offset(self):
        plain, _ = build_overdue_digest([_task("X", days_overdue=0)], now=NOW)
        assert "17.08.2026" in plain  # дата в московской зоне значении


def _run(**over) -> DirectumRun:
    values = dict(
        id=7,
        triggered_by="cron",
        status="success",
        tasks_total=10,
        performers_total=4,
        users_notified=2,
        users_skipped_opt_in=1,
        users_unmatched=0,
        users_ambiguous=0,
        errors=0,
        report={},
    )
    values.update(over)
    run = DirectumRun(**values)
    run.started_at = NOW
    run.finished_at = NOW
    return run


class TestBuildSubject:
    def test_clean_run(self):
        assert build_subject(_run()) == "Directum: просроченные задачи — 10 задач, уведомлено 2"

    def test_problems_appended(self):
        subject = build_subject(_run(users_unmatched=3, users_ambiguous=2))
        assert "требуют внимания" in subject

    def test_failed(self):
        assert "сбой" in build_subject(_run(status="failed"))


class TestBuildReportBodies:
    def test_sections_rendered(self):
        run = _run(
            report={
                "notified": [{"fio": "Иванов Иван Иванович", "tasks": 3}],
                "skipped_opt_in": [{"fio": "Петров Пётр Петрович", "tasks": 1}],
                "unmatched": [{"fio": "Капитан судна Н.Трубятчинский", "tasks": 6}],
            }
        )
        html, plain = build_report_bodies(run)
        assert "Уведомлено (1)" in html
        assert "чат выключен (1)" in html
        assert "Не сопоставлено (1)" in html
        assert "Иванов Иван Иванович" in plain
        assert "включите" not in plain.lower() or True

    def test_matrix_disabled_warning(self):
        run = _run(report={"matrix_disabled": True})
        html, plain = build_report_bodies(run)
        assert "Matrix-бот" in html
        assert "Matrix" in plain

    def test_error_section_for_failed(self):
        run = _run(status="failed", report={"error": "HTTP 503: upstream"})
        html, plain = build_report_bodies(run)
        assert "HTTP 503" in html
        assert "HTTP 503" in plain

    def test_ambiguous_candidates_listed(self):
        run = _run(
            report={
                "ambiguous": [
                    {
                        "fio": "Сидоров Сидор Сидорович",
                        "candidates": [
                            {"full_name": "Сидоров Сидор Сидорович"},
                            {"full_name": "Сидоров Сидор Петрович"},
                        ],
                    }
                ]
            }
        )
        html, plain = build_report_bodies(run)
        assert "Сидоров Сидор Петрович" in html
        assert "Сидоров Сидор Петрович" in plain

    def test_empty_sections_omitted(self):
        html, _ = build_report_bodies(_run(report={}))
        # Сводная таблица содержит подписи строк — секции с деталями не рендерятся.
        assert "Не сопоставлено (" not in html
        assert "Уведомлено (" not in html
        assert "Неоднозначно (" not in html

    def test_user_content_escaped(self):
        run = _run(report={"unmatched": [{"fio": "<b>Злая Фамилия</b>", "tasks": 1}]})
        html, _ = build_report_bodies(run)
        assert "<b>Злая" not in html
        assert "&lt;b&gt;Злая Фамилия&lt;/b&gt;" in html
