"""Persist diagnostics for rejected incoming helpdesk attachments.

Revision ID: 095
Revises: 094
Create Date: 2026-08-13
"""

from alembic import op

revision: str = "095"
down_revision: str | None = "094"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE helpdesk_messages "
        "ADD COLUMN IF NOT EXISTS attachment_warnings JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE helpdesk_messages DROP COLUMN IF EXISTS attachment_warnings")
