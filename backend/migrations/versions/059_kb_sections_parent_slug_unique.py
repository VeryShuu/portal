"""
Revision ID: 059
Revises: 058
Create Date: 2026-05-24
"""

from alembic import op

revision: str = "059"
down_revision: str | None = "058"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_kb_sections_slug", "kb_sections", type_="unique")
    op.create_unique_constraint(
        "uq_kb_sections_parent_slug",
        "kb_sections",
        ["parent_id", "slug"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_kb_sections_parent_slug", "kb_sections", type_="unique")
    op.create_unique_constraint("uq_kb_sections_slug", "kb_sections", ["slug"])
