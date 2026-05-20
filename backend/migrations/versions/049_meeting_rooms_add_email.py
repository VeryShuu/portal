"""meeting_rooms: add email column

Revision ID: 049
Revises: 048
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from alembic import op

revision: str = "049"
down_revision: str | None = "048"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("meeting_rooms", sa.Column("email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("meeting_rooms", "email")
