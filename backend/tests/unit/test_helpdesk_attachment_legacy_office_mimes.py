"""Регрессия legacy Office-вложений, полученных через email-ingress."""

from __future__ import annotations

from app.services.helpdesk.attachments import _effective_ingress_mime


class TestLegacyOfficeMimeNormalization:
    def test_accepts_doc_when_ole_magic_and_declared_mime_match(self) -> None:
        """libmagic даёт generic OLE для корректного старого ``.doc``."""
        assert (
            _effective_ingress_mime(
                detected_mime="application/x-ole-storage",
                declared_content_type="application/msword",
                original_name="М-0258 Владимир Загоскин.doc",
            )
            == "application/msword"
        )

    def test_rejects_ole_when_declared_mime_does_not_match_suffix(self) -> None:
        """Нельзя разрешить любой OLE-контейнер только по расширению."""
        assert (
            _effective_ingress_mime(
                detected_mime="application/x-ole-storage",
                declared_content_type="application/octet-stream",
                original_name="suspicious.doc",
            )
            == "application/x-ole-storage"
        )

    def test_rejects_ole_when_suffix_does_not_match_declared_mime(self) -> None:
        assert (
            _effective_ingress_mime(
                detected_mime="application/x-ole-storage",
                declared_content_type="application/msword",
                original_name="suspicious.xls",
            )
            == "application/x-ole-storage"
        )
