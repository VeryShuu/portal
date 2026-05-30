"""KB media URL helpers used by export routes (PDF/DOCX inlining)."""

from __future__ import annotations

import base64
import mimetypes
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

KB_MEDIA_URL_RE = re.compile(
    r"/api/v1/kb/media/([0-9a-fA-F-]{36})/([\w.\-]{1,255})"
)


def kb_media_path(article_id: uuid.UUID, filename: str) -> Path | None:
    """Resolve a local file path for a KB media reference, guarding against traversal."""
    if not re.fullmatch(r"\w[\w.\-]{0,254}", filename) or "/" in filename or "\\" in filename:
        return None
    base = Path(get_settings().kb_media_dir).resolve()
    candidate = (base / str(article_id) / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def kb_media_data_uri(article_id: uuid.UUID, filename: str) -> str | None:
    path = kb_media_path(article_id, filename)
    if path is None:
        return None
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def inline_kb_media_as_data_uris(text_value: str) -> str:
    """Replace ``/api/v1/kb/media/<uuid>/<file>`` URLs with inline ``data:`` URIs.

    The screenshot-service used for PDF rendering blocks all network requests,
    so images referenced by HTTP URL cannot load. Inlining as data URIs lets
    the headless browser render them directly.
    """
    def _repl(match: re.Match[str]) -> str:
        try:
            art_id = uuid.UUID(match.group(1))
        except ValueError:
            return match.group(0)
        data_uri = kb_media_data_uri(art_id, match.group(2))
        return data_uri or match.group(0)

    return KB_MEDIA_URL_RE.sub(_repl, text_value)
