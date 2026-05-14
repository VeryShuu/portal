"""Generate Markdown documentation for all SQLAlchemy models.

Usage (from ./backend/):
    python -m scripts.generate_db_schema_doc > ../docs/db-schema.generated.md
    python -m scripts.generate_db_schema_doc --output ../docs/db-schema.generated.md
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "x" * 32)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from sqlalchemy.orm import RelationshipProperty

import app.models.feedback
import app.models.files
import app.models.kb
import app.models.links
import app.models.news
import app.models.notification
import app.models.photos
import app.models.user
import app.models.user_attribute_mapping  # noqa: F401
from app.core.database import Base


def _col_type_str(col: sa.Column) -> str:
    try:
        return str(col.type.compile(dialect=sa.dialects.postgresql.dialect()))
    except Exception:
        return str(col.type)


def _default_str(col: sa.Column) -> str:
    if col.server_default is not None:
        sd = col.server_default
        if hasattr(sd, "arg"):
            arg = sd.arg
            if hasattr(arg, "text"):
                return f"`{arg.text}`"
            return f"`{arg}`"
        return str(sd)
    if col.default is not None:
        d = col.default
        if hasattr(d, "arg"):
            arg = d.arg
            if callable(arg):
                return "<function>"
            return f"`{arg}`"
    return ""


def _fk_str(col: sa.Column) -> str:
    fks = list(col.foreign_keys)
    if not fks:
        return ""
    return ", ".join(f"`{fk.target_fullname}`" for fk in fks)


def _table_section(table: sa.Table, mapper_map: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"## `{table.name}`\n")

    mapper = mapper_map.get(table.name)
    if mapper and mapper.class_.__doc__:
        doc = mapper.class_.__doc__.strip()
        if doc:
            lines.append(f"{doc}\n")

    lines.append("### Columns\n")
    lines.append("| Column | Type | Nullable | PK | FK | Unique | Default | Comment |")
    lines.append("|--------|------|----------|----|----|--------|---------|---------|")

    for col in table.columns:
        pk = "✓" if col.primary_key else ""
        nullable = "✓" if col.nullable else ""
        unique = "✓" if col.unique else ""
        fk = _fk_str(col)
        default = _default_str(col)
        comment = col.comment or ""
        col_type = _col_type_str(col)
        lines.append(
            f"| `{col.name}` | `{col_type}` | {nullable} | {pk} | {fk} | {unique} | {default} | {comment} |"
        )

    constraints = [
        c
        for c in table.constraints
        if not isinstance(c, sa.PrimaryKeyConstraint)
        and not isinstance(c, sa.ForeignKeyConstraint)
    ]
    if constraints:
        lines.append("\n### Constraints\n")
        lines.append("| Name | Type | Definition |")
        lines.append("|------|------|------------|")
        for c in constraints:
            if isinstance(c, sa.CheckConstraint):
                name = c.name or ""
                lines.append(f"| `{name}` | CHECK | `{c.sqltext}` |")
            elif isinstance(c, sa.UniqueConstraint):
                name = c.name or ""
                cols = ", ".join(f"`{col.name}`" for col in c.columns)
                lines.append(f"| `{name}` | UNIQUE | {cols} |")

    if table.indexes:
        lines.append("\n### Indexes\n")
        lines.append("| Name | Columns | Unique |")
        lines.append("|------|---------|--------|")
        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            unique = "✓" if idx.unique else ""
            try:
                col_list = ", ".join(f"`{e.key}`" if hasattr(e, "key") else str(e) for e in idx.expressions)
            except Exception:
                col_list = str(idx.expressions)
            lines.append(f"| `{idx.name}` | {col_list} | {unique} |")

    if mapper:
        rels = [
            (key, rel)
            for key, rel in mapper.relationships.items()
            if isinstance(rel, RelationshipProperty)
        ]
        if rels:
            lines.append("\n### Relationships\n")
            lines.append("| Attribute | Target | Type | Back-populates |")
            lines.append("|-----------|--------|------|----------------|")
            for key, rel in rels:
                target = rel.mapper.class_.__name__
                uselist = "one-to-many" if rel.uselist else "many-to-one"
                bp = rel.back_populates or ""
                lines.append(f"| `{key}` | `{target}` | {uselist} | `{bp}` |")

    lines.append("")
    return "\n".join(lines)


def _mermaid_er(tables: list[sa.Table]) -> str:
    lines: list[str] = ["```mermaid", "erDiagram"]
    seen_rels: set[tuple[str, str]] = set()

    for table in tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                ref_table = fk.column.table.name
                pair = (table.name, ref_table)
                if pair not in seen_rels:
                    seen_rels.add(pair)
                    label = f"FK {col.name}"
                    lines.append(f'    {table.name} ||--o{{ {ref_table} : "{label}"')

    lines.append("```")
    return "\n".join(lines)


def generate(output: Path | None) -> None:
    metadata = Base.metadata

    tables = sorted(metadata.tables.values(), key=lambda t: t.name)

    registry = Base.registry
    mapper_map: dict[str, Any] = {}
    for mapper in registry.mappers:
        tname = mapper.local_table.name
        mapper_map[tname] = mapper

    check_constraints: dict[str, list[str]] = {}
    for table in tables:
        vals: list[str] = []
        for c in table.constraints:
            if isinstance(c, sa.CheckConstraint):
                text = str(c.sqltext)
                import re
                m = re.search(r"IN \(([^)]+)\)", text)
                if m:
                    vals_str = m.group(1)
                    vals.extend(v.strip().strip("'") for v in vals_str.split(","))
        if vals:
            check_constraints[table.name] = vals

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out: list[str] = [
        "<!-- AUTO-GENERATED — do not edit manually. Run: cd backend && python -m scripts.generate_db_schema_doc --output ../docs/db-schema.generated.md -->",
        f"<!-- Generated: {now} -->",
        "",
        "# Database Schema (auto-generated)",
        "",
        "> Generated from SQLAlchemy models in `./backend/app/models/`  \n> Source of truth: `./docs/db-schema.generated.md` (auto) and `./docs/db-schema.md` (curated).",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
    ]

    for table in tables:
        anchor = table.name.replace("_", "-")
        out.append(f"- [`{table.name}`](#{anchor})")

    out.append("")
    out.append("---")
    out.append("")
    out.append("## ER Diagram (FK graph)")
    out.append("")
    out.append(_mermaid_er(tables))
    out.append("")
    out.append("---")
    out.append("")

    for table in tables:
        out.append(_table_section(table, mapper_map))
        out.append("---")
        out.append("")

    content = "\n".join(out)

    if output:
        output.write_text(content, encoding="utf-8")
        size = output.stat().st_size
        print(
            f"DB schema doc written: {output} ({size} bytes, {len(tables)} tables)",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DB schema Markdown from SQLAlchemy models")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    if args.output is None and sys.stdout.isatty():
        default = Path(__file__).resolve().parents[2] / "docs" / "db-schema.generated.md"
        args.output = default

    generate(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
