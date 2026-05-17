"""add cover_focal_point to news

Revision ID: 027
Revises: 026
Create Date: 2026-05-03
"""


import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("news", sa.Column("cover_focal_point", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("news", "cover_focal_point")
