"""Add deleted_at to kb_sections for soft delete

Revision ID: 036
Revises: 035
Create Date: 2026-05-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_sections", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "idx_kb_sections_deleted",
        "kb_sections",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_kb_sections_deleted", table_name="kb_sections")
    op.drop_column("kb_sections", "deleted_at")
