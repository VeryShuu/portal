"""Unit-тесты сертификатов (этап 2): HTML-шаблон с экранированием, серийный
номер, канонический путь файла."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from app.models.learning import LearningCertificate
from app.services.learning import certificates as cert_svc
from app.services.learning import courses_service as cs


class TestCertificateHtml:
    def test_escapes_participant_and_course(self):
        html = cert_svc.certificate_html(
            serial="LC-ABCD1234",
            participant_name="<script>alert(1)</script>",
            course_title="Курс & «кавычки»",
            issued_at=datetime(2026, 8, 29, tzinfo=UTC),
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "Курс &amp; «кавычки»" in html
        assert "LC-ABCD1234" in html
        assert "29.08.2026" in html

    def test_contains_certificate_fields(self):
        html = cert_svc.certificate_html(
            serial="LC-X",
            participant_name="Иван Иванов",
            course_title="Охрана труда",
            issued_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        )
        assert "Иван Иванов" in html
        assert "«Охрана труда»" in html


class TestSerial:
    def test_format_and_uniqueness(self):
        a = cert_svc._serial()
        b = cert_svc._serial()
        assert a.startswith("LC-") and len(a) == 11
        # без неоднозначных символов
        assert not set(a[3:]) & {"0", "O", "1", "I", "L"}
        assert a != b or len(set("23456789ABCDEFGHJKMNPQRSTUVWXYZ")) == 1


class TestResolvePath:
    def test_none_on_foreign_path_or_missing_file(self, tmp_path: Path, monkeypatch):

        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        course_id, cert_id = uuid.uuid4(), uuid.uuid4()
        stub = SimpleNamespace(course_id=course_id, id=cert_id, pdf_path="/etc/passwd")
        cert = cast(LearningCertificate, stub)
        assert cert_svc.resolve_certificate_path(cert) is None

        stub.pdf_path = str(cert_svc.certificate_pdf_path(course_id, cert_id))
        assert cert_svc.resolve_certificate_path(cert) is None  # файла нет

        cert_svc.certificate_pdf_path(course_id, cert_id).parent.mkdir(parents=True)
        cert_svc.certificate_pdf_path(course_id, cert_id).write_bytes(b"pdf")
        assert cert_svc.resolve_certificate_path(cert) is not None
