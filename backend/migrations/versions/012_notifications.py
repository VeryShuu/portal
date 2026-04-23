"""Add notifications table

Revision ID: 012
Revises: 011
Create Date: 2026-04-23

Phase 4: in-app + email notifications system.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notifications (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type        VARCHAR(80) NOT NULL,
            title       VARCHAR(500) NOT NULL,
            body        TEXT,
            link        VARCHAR(1000),
            is_read     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            read_at     TIMESTAMP WITH TIME ZONE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_notifications_user_unread ON notifications(user_id, created_at DESC) WHERE is_read = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_notifications_user_all ON notifications(user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
