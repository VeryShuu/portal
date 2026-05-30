"""meetings module: rooms, bookings, booking_rooms, audit_log

Revision ID: 048
Revises: 047
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "048"
down_revision: str | None = "047"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "meeting_rooms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("link", sa.String(2048), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("name", name="uq_meeting_rooms_name"),
    )
    op.create_index("idx_meeting_rooms_active", "meeting_rooms", ["is_active"])
    op.create_index("idx_meeting_rooms_sort", "meeting_rooms", ["sort_order", "name"])

    op.create_table(
        "meeting_bookings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("organizer_name", sa.String(255), nullable=False),
        sa.Column(
            "creator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invited_users",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("update_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("end_time > start_time", name="ck_meeting_bookings_time_order"),
    )
    op.create_index("idx_meeting_bookings_time", "meeting_bookings", ["start_time", "end_time"])
    op.create_index("idx_meeting_bookings_series", "meeting_bookings", ["series_id"])
    op.create_index("idx_meeting_bookings_creator", "meeting_bookings", ["creator_id"])
    op.create_index(
        "idx_meeting_bookings_time_range",
        "meeting_bookings",
        [sa.text("tstzrange(start_time, end_time)")],
        postgresql_using="gist",
    )

    op.create_table(
        "meeting_booking_rooms",
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meeting_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meeting_rooms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("booking_id", "room_id"),
    )
    op.create_index("idx_meeting_booking_rooms_room", "meeting_booking_rooms", ["room_id"])
    op.execute(
        """
        ALTER TABLE meeting_booking_rooms
        ADD CONSTRAINT booking_rooms_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            tstzrange(start_time, end_time, '[)') WITH &&
        )
        """
    )

    op.create_table(
        "meetings_audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("user_email", sa.String(320), nullable=True),
        sa.Column("user_role", sa.String(32), nullable=True),
        sa.Column("resource_type", sa.String(32), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_title", sa.String(500), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_meetings_audit_timestamp",
        "meetings_audit_log",
        [sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_meetings_audit_action_ts",
        "meetings_audit_log",
        ["action", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_meetings_audit_user_ts",
        "meetings_audit_log",
        ["user_id", sa.text("timestamp DESC")],
    )


def downgrade() -> None:
    op.drop_table("meetings_audit_log")
    op.execute(
        "ALTER TABLE meeting_booking_rooms DROP CONSTRAINT IF EXISTS booking_rooms_no_overlap"
    )
    op.drop_table("meeting_booking_rooms")
    op.drop_table("meeting_bookings")
    op.drop_table("meeting_rooms")
