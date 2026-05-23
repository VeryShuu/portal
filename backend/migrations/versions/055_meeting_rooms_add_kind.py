"""meeting_rooms: add kind column (physical/virtual)

Revision ID: 055
Revises: 054
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision: str = "055"
down_revision: str | None = "054"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "meeting_rooms",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default="physical",
        ),
    )
    # Heuristic: rooms with a link are likely virtual (e.g. Zoom).
    op.execute(
        "UPDATE meeting_rooms SET kind = 'virtual' "
        "WHERE link IS NOT NULL AND length(trim(link)) > 0"
    )
    op.create_check_constraint(
        "ck_meeting_rooms_kind",
        "meeting_rooms",
        "kind IN ('physical', 'virtual')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_meeting_rooms_kind", "meeting_rooms", type_="check")
    op.drop_column("meeting_rooms", "kind")
