"""add cover_image to news

Revision ID: 005
Revises: 004
Create Date: 2026-04-22
"""


import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("news", sa.Column("cover_image", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("news", "cover_image")
