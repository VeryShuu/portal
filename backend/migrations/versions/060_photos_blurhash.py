"""
Revision ID: 060
Revises: 059
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op

revision: str = "060"
down_revision: str | None = "059"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("blurhash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "blurhash")
