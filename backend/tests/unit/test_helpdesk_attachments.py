"""Unit-тесты сервиса helpdesk-вложений (Этап 4, Б4).

Без БД: проверяют чистые функции — path-traversal guard на ``disk_path``,
формат безопасного имени ``_safe_stored_name``, лимиты размера (константы).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from app.services.helpdesk import attachments as att_service
from app.services.helpdesk.attachments import (
    _MAX_ATTACHMENT_BYTES,
    _MAX_TOTAL_BYTES,
    _SAFE_FILENAME_RE,
    _safe_stored_name,
    _TotalTracker,
    delete_attachment_files,
    disk_path,
    save_image_bytes,
    ticket_dir,
)


class TestSafeStoredName:
    def test_strips_path_components(self) -> None:
        # Только базовое имя, без каталогов.
        name = _safe_stored_name("../../etc/passwd")
        assert "/" not in name
        assert ".." not in name

    def test_sanitizes_special_chars(self) -> None:
        name = _safe_stored_name("file with spaces!.pdf")
        assert " " not in name
        assert "!" not in name

    def test_uuid_prefix_present(self) -> None:
        name = _safe_stored_name("doc.pdf")
        # Формат: {32 hex}_{sanitized}
        prefix = name.split("_", 1)[0]
        assert len(prefix) == 32
        # Валидный hex.
        int(prefix, 16)

    def test_empty_filename_fallback(self) -> None:
        name = _safe_stored_name("")
        assert name.endswith("_file") or "file" in name


class TestDiskPathGuard:
    def _att(self, filename: str):
        from app.models.helpdesk import HelpdeskAttachment

        return HelpdeskAttachment(
            ticket_id=uuid.uuid4(),
            filename=filename,
            original_name="x",
            content_type="text/plain",
            size_bytes=1,
        )

    def test_safe_filename_accepted(self) -> None:
        path = disk_path(self._att("abc_123.txt"), 42)
        assert path.name == "abc_123.txt"
        assert path.parent == ticket_dir(42)

    @pytest.mark.parametrize(
        "bad",
        [
            "../../../etc/passwd",
            "a/b",
            "a\\b",
            "a b",  # пробел
            ".hidden",  # начинается с точки
            "",  # пусто
        ],
    )
    def test_path_traversal_rejected(self, bad: str) -> None:
        # Проверяем, что regex guard отклоняет опасные/невалидные имена.
        assert not _SAFE_FILENAME_RE.match(bad)
        with pytest.raises(HTTPException) as exc:
            disk_path(self._att(bad), 42)
        assert exc.value.status_code == 400

    def test_ticket_dir_uses_tkt_prefix(self) -> None:
        assert ticket_dir(123).name == "TKT-123"


class TestSizeLimits:
    def test_max_attachment_bytes_from_constants(self) -> None:
        from app.core.constants import HELPDESK_MAX_ATTACHMENT_MB

        assert _MAX_ATTACHMENT_BYTES == HELPDESK_MAX_ATTACHMENT_MB * 1024 * 1024

    def test_max_total_bytes_from_constants(self) -> None:
        from app.core.constants import HELPDESK_MAX_TOTAL_INGRESS_MB

        assert _MAX_TOTAL_BYTES == HELPDESK_MAX_TOTAL_INGRESS_MB * 1024 * 1024


@pytest.mark.asyncio
class TestIngressAttachmentDiagnostics:
    @staticmethod
    def _ticket() -> Any:
        return SimpleNamespace(number=42)

    async def test_reports_rejected_mime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(att_service, "_detect_mime", lambda _data: "application/x-msdownload")
        warnings: list[str] = []

        result = await save_image_bytes(
            cast(Any, object()),
            ticket=self._ticket(),
            message_id=uuid.uuid4(),
            data=b"not-an-executable",
            original_name="unsafe.exe",
            rejection_sink=warnings,
        )

        assert result is None
        assert warnings == ["Вложение «unsafe.exe» не сохранено: неподдерживаемый тип файла."]

    async def test_reports_file_too_large(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(att_service, "_detect_mime", lambda _data: "application/pdf")
        warnings: list[str] = []

        result = await save_image_bytes(
            cast(Any, object()),
            ticket=self._ticket(),
            message_id=uuid.uuid4(),
            data=b"x" * (_MAX_ATTACHMENT_BYTES + 1),
            original_name="oversize.pdf",
            rejection_sink=warnings,
        )

        assert result is None
        assert warnings == ["Вложение «oversize.pdf» не сохранено: размер файла превышает 25 МБ."]

    async def test_reports_total_limit_exceeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(att_service, "_detect_mime", lambda _data: "application/pdf")
        warnings: list[str] = []
        tracker = _TotalTracker()
        tracker.total = _MAX_TOTAL_BYTES

        result = await save_image_bytes(
            cast(Any, object()),
            ticket=self._ticket(),
            message_id=uuid.uuid4(),
            data=b"x",
            original_name="one-more.pdf",
            total_tracker=tracker,
            rejection_sink=warnings,
        )

        assert result is None
        assert warnings == [
            "Вложение «one-more.pdf» не сохранено: превышен общий лимит вложений письма (50 МБ)."
        ]


class TestDeleteFiles:
    def test_delete_ignores_invalid_names(self, tmp_path) -> None:
        # Невалидные имена молча пропускаются (best-effort cleanup).
        with pytest.MonkeyPatch().context() as ctx:
            ctx.setattr(att_service, "HELPDESK_FILES_DIR", tmp_path)
            (ticket_dir(1) / "valid.txt").parent.mkdir(parents=True, exist_ok=True)
            (ticket_dir(1) / "valid.txt").write_text("x")
            # Невалидное имя не должно вызывать исключение.
            delete_attachment_files(1, ["valid.txt", "../../../etc/passwd", ""])
            assert not (ticket_dir(1) / "valid.txt").exists()
