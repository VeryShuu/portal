"""KB export builders: filesystem-safe document/stem names.

Pure logic with no HTTP layer; the API handlers add ACL and audit. PDF/DOCX
rendering lives in ``app.api.kb._pdf_export`` / ``app.api.kb._docx_export``.
"""

from __future__ import annotations

import re


def article_md_stem(title: str) -> str:
    """Filesystem-safe stem for a single-article Markdown export."""
    return re.sub(r"[^\w\- ]", "", title)[:60].strip() or "article"


def section_zip_stem(title: str) -> str:
    """Filesystem-safe stem for a section ZIP export."""
    return re.sub(r"[^\w\- ]", "", title)[:40] or "section"


def document_stem(title: str) -> str:
    """Filesystem-safe stem for PDF/DOCX document exports."""
    return re.sub(r"[^\w\s-]", "", title)[:80].strip() or "article"
