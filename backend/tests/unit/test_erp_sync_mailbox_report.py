"""Unit-тесты mailbox-фильтрации и HTML-отчёта (services/erp_sync/).

Покрытие:

* :mod:`mailbox` — post-fetch фильтры (subject/sender/attachment), MIME-
  декодирование заголовков, выбор вложения.
* :mod:`report` — построение HTML/plain тел письма, экранирование XSS,
  сводка, diff old→new.

Чистые функции — без БД/Redis.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")

from email.message import EmailMessage

from app.services.erp_sync.mailbox import _matches_filters, _pick_attachment
from app.services.erp_sync.report import (
    _fmt_value,
    _gender_label,
    build_report_bodies,
    build_subject,
)

# ── mailbox: _matches_filters ────────────────────────────────────────────────


def _msg(
    *, subject: str = "Отчёт по сотрудникам", sender: str = "erp@company.local"
) -> EmailMessage:
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = f"ERP System <{sender}>"
    m["To"] = "portal@company.local"
    m.set_content("See attachment")
    return m


class TestMatchesFilters:
    def test_no_filters_passes_all(self):
        assert _matches_filters(_msg(), subject_filter=None, sender_filter=None) is True

    def test_subject_match(self):
        assert _matches_filters(_msg(), subject_filter="сотрудник", sender_filter=None) is True

    def test_subject_case_insensitive(self):
        assert (
            _matches_filters(
                _msg(subject="ОТЧЁТ ПО СОТРУДНИКАМ"),
                subject_filter="сотрудникам",
                sender_filter=None,
            )
            is True
        )

    def test_subject_no_match(self):
        assert (
            _matches_filters(
                _msg(subject="Прайс-лист"), subject_filter="сотрудник", sender_filter=None
            )
            is False
        )

    def test_sender_match(self):
        assert (
            _matches_filters(
                _msg(sender="erp@firm.local"), subject_filter=None, sender_filter="erp@firm.local"
            )
            is True
        )

    def test_sender_substring(self):
        assert (
            _matches_filters(
                _msg(sender="noreply@erp.firm.local"), subject_filter=None, sender_filter="erp.firm"
            )
            is True
        )

    def test_sender_no_match(self):
        assert (
            _matches_filters(
                _msg(sender="spam@spam.local"), subject_filter=None, sender_filter="erp@firm.local"
            )
            is False
        )

    def test_both_filters_and(self):
        """Все заданные фильтры должны совпасть (AND-логика)."""
        assert (
            _matches_filters(
                _msg(subject="Сотрудники", sender="erp@firm.local"),
                subject_filter="сотрудники",
                sender_filter="erp@firm.local",
            )
            is True
        )
        # Subject совпал, sender нет → False.
        assert (
            _matches_filters(
                _msg(subject="Сотрудники", sender="spam@spam.local"),
                subject_filter="сотрудники",
                sender_filter="erp@firm.local",
            )
            is False
        )

    def test_mime_encoded_subject(self):
        """Тема с RFC 2047 encoded-word (=?UTF-8?B?...?=) декодируется."""
        import base64

        encoded = base64.b64encode("Сотрудники отчёт".encode()).decode("ascii")
        msg = _msg(subject=f"=?UTF-8?B?{encoded}?=")
        assert _matches_filters(msg, subject_filter="отчёт", sender_filter=None) is True


# ── mailbox: _pick_attachment ────────────────────────────────────────────────


def _msg_with_attachment(filename: str, content: bytes = b"data") -> EmailMessage:
    m = _msg()
    m.add_attachment(content, maintype="application", subtype="octet-stream", filename=filename)
    return m


class TestPickAttachment:
    def test_supported_format_no_filter(self):
        msg = _msg_with_attachment("report.xlsx")
        picked = _pick_attachment(msg, attachment_filter=None)
        assert picked is not None
        assert picked[0] == "report.xlsx"

    def test_attachment_filter_match(self):
        msg = _msg_with_attachment("Сотрудники_август.xlsx")
        picked = _pick_attachment(msg, attachment_filter="Сотрудники")
        assert picked is not None
        assert "Сотрудники" in picked[0]

    def test_attachment_filter_no_match(self):
        msg = _msg_with_attachment("prices.xlsx")
        picked = _pick_attachment(msg, attachment_filter="Сотрудники")
        assert picked is None

    def test_unsupported_format_skipped_without_filter(self):
        """Без явного фильтра — только поддерживаемые расширения."""
        msg = _msg_with_attachment("report.pdf")
        picked = _pick_attachment(msg, attachment_filter=None)
        assert picked is None

    def test_picks_first_supported(self):
        """Несколько вложений → первое поддерживаемое."""
        m = _msg()
        m.add_attachment(b"a", maintype="application", subtype="octet-stream", filename="notes.pdf")
        m.add_attachment(b"b", maintype="application", subtype="octet-stream", filename="data.xlsx")
        picked = _pick_attachment(m, attachment_filter=None)
        assert picked is not None
        assert picked[0] == "data.xlsx"

    def test_no_attachment(self):
        msg = _msg()
        assert _pick_attachment(msg, attachment_filter=None) is None


# ── report ───────────────────────────────────────────────────────────────────


class TestReportBodies:
    def test_subject_no_problems(self):
        from datetime import UTC, datetime

        from app.models.erp_sync import ErpSyncRun

        run = ErpSyncRun(
            triggered_by="cron",
            started_at=datetime.now(UTC),
            status="success",
            rows_updated=10,
            rows_total=10,
        )
        assert "10 обновлено" in build_subject(run)
        assert "внимания" not in build_subject(run)

    def test_subject_with_problems(self):
        from datetime import UTC, datetime

        from app.models.erp_sync import ErpSyncRun

        run = ErpSyncRun(
            triggered_by="cron",
            started_at=datetime.now(UTC),
            status="partial",
            rows_updated=5,
            rows_unmatched=2,
            rows_ambiguous=1,
        )
        subj = build_subject(run)
        assert "5 обновлено" in subj
        assert "требуют внимания" in subj

    def test_build_bodies_has_summary(self):
        run = self._make_run(rows_updated=3, rows_unmatched=1)
        html, plain = build_report_bodies(run)
        assert "Всего строк в файле" in html
        assert "Всего:" in plain

    def test_build_bodies_escapes_xss(self):
        """ФИО с <script> должно быть экранировано в HTML."""
        run = self._make_run(rows_updated=1)
        run.report = {
            "changed": [
                {
                    "fio": "<script>alert(1)</script>",
                    "user_id": "u1",
                    "fields": {"birth_date": {"old": None, "new": "1990-01-01"}},
                }
            ],
            "unmatched": [],
            "ambiguous": [],
            "conflicts": [],
            "errors": [],
        }
        html, _ = build_report_bodies(run)
        assert "<script>alert(1)</script>" not in html  # сырой тег не прошёл
        assert "&lt;script&gt;" in html  # экранированный есть

    def test_build_bodies_includes_sections(self):
        run = self._make_run(rows_updated=1, rows_unmatched=1, rows_ambiguous=1)
        run.report = {
            "changed": [
                {
                    "fio": "Иванов Иван",
                    "user_id": "u1",
                    "fields": {
                        "birth_date": {"old": "1985-05-05", "new": "1990-01-01"},
                        "gender": {"old": "female", "new": "male"},
                    },
                }
            ],
            "unmatched": [{"fio": "Неттаков Нетак", "birth_date": "2000-01-01", "gender": "male"}],
            "ambiguous": [
                {
                    "fio": "Петров Пётр",
                    "candidates": [{"full_name": "Петров Пётр А"}, {"full_name": "Петров Пётр Б"}],
                }
            ],
            "conflicts": [],
            "errors": [{"raw": "битая строка", "reason": "дата не распознана"}],
        }
        html, plain = build_report_bodies(run)
        assert "Обновлено" in html
        assert "Иванов Иван" in html
        assert "1985-05-05" in html  # old value в diff
        assert "1990-01-01" in html  # new value
        assert "Мужской" in html  # gender label для new=male
        assert "Не сопоставлено" in html
        assert "Неттаков Нетак" in html
        assert "Неоднозначно" in html
        # plain тоже содержит ключевые данные
        assert "Иванов Иван" in plain
        assert "Неттаков Нетак" in plain

    def _make_run(self, **kwargs):
        from datetime import UTC, datetime

        from app.models.erp_sync import ErpSyncRun

        defaults = dict(
            triggered_by="cron",
            started_at=datetime.now(UTC),
            status="partial",
            rows_total=0,
            rows_matched=0,
            rows_updated=0,
            rows_unmatched=0,
            rows_ambiguous=0,
            conflicts=0,
            errors=0,
            report={},
        )
        defaults.update(kwargs)
        return ErpSyncRun(**defaults)


class TestReportHelpers:
    def test_gender_label(self):
        assert _gender_label("male") == "Мужской"
        assert _gender_label("female") == "Женский"
        assert _gender_label(None) == ""  # type: ignore[arg-type]

    def test_fmt_value_none(self):
        assert _fmt_value(None) == "—"

    def test_fmt_value_date(self):
        from datetime import date

        assert _fmt_value(date(1990, 1, 1)) == "1990-01-01"
