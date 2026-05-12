"""news: add previous_status column

Revision ID: 043
Revises: 042
Create Date: 2026-05-12

Stores the status value that was active immediately before a soft-delete so
that restore_news can return the record to its original state.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("news", sa.Column("previous_status", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("news", "previous_status")
