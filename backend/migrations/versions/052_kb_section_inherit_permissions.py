"""kb_sections: add inherit_permissions column

Revision ID: 052
Revises: 051
Create Date: 2026-05-21

When inherit_permissions is TRUE (default) the section inherits ACL from its
parent — the existing recursive CTE walks up the ancestor chain.
When FALSE the resolution stops at this section: only direct permissions on
the section itself are considered, regardless of what is set on any parent.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "052"
down_revision: str | None = "051"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "kb_sections",
        sa.Column(
            "inherit_permissions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )


def downgrade() -> None:
    op.drop_column("kb_sections", "inherit_permissions")
