"""
Revision ID: 058
Revises: 057
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision: str = "058"
down_revision: str | None = "057"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("UPDATE kb_article_versions SET body = '' WHERE body IS NULL")
    op.alter_column("kb_article_versions", "body", nullable=False, existing_type=sa.Text())


def downgrade() -> None:
    op.alter_column("kb_article_versions", "body", nullable=True, existing_type=sa.Text())
