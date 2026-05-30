"""Recursive CTE helpers for the kb_sections tree.

Centralises the SQL text used to walk descendants/ancestors of a section node,
to avoid drift between callers. All helpers return SQL strings (and the bound
parameter names) suitable for `db.execute(text(...), {...})`.
"""

from __future__ import annotations

# Walk descendants (subtree) starting from a single root section id.
# Bind: :section_id (str).
KB_SECTIONS_DESCENDANTS_SQL = """
WITH RECURSIVE descendants AS (
    SELECT id FROM kb_sections
    WHERE id = :section_id AND deleted_at IS NULL
    UNION ALL
    SELECT s.id FROM kb_sections s
    JOIN descendants d ON s.parent_id = d.id
    WHERE s.deleted_at IS NULL
)
SELECT id FROM descendants
"""


# Walk ancestors (path to root) of a single section id.
# Bind: :section_id (str).
KB_SECTIONS_ANCESTORS_SQL = """
WITH RECURSIVE ancestors AS (
    SELECT id, parent_id FROM kb_sections
    WHERE id = :section_id AND deleted_at IS NULL
    UNION ALL
    SELECT s.id, s.parent_id FROM kb_sections s
    JOIN ancestors a ON s.id = a.parent_id
    WHERE s.deleted_at IS NULL
)
SELECT id FROM ancestors
"""


__all__ = [
    "KB_SECTIONS_ANCESTORS_SQL",
    "KB_SECTIONS_DESCENDANTS_SQL",
]
