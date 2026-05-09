"""Backward-compatibility shim.

All KB endpoints were merged into the ``app.api.kb`` package (task 1.1.d).
This module re-exports symbols still referenced by tests and external code.
"""

from app.api.kb._common import _rfc5987_filename, _slugify
from app.api.kb._frontmatter import _build_frontmatter, _parse_frontmatter
from app.schemas.kb_extra import DiffHunk, DiffResponse

__all__ = [
    "DiffHunk",
    "DiffResponse",
    "_build_frontmatter",
    "_parse_frontmatter",
    "_rfc5987_filename",
    "_slugify",
]
