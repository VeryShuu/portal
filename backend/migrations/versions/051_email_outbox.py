"""email outbox table (transactional outbox for all outgoing email)

Revision ID: 051
Revises: 050
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "051"
down_revision: str | None = "050"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_type", sa.String(128), nullable=True),
        sa.Column("last_error_class", sa.String(16), nullable=True),
        sa.Column("related_resource_type", sa.String(64), nullable=True),
        sa.Column("related_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','SENT','FAILED','DLQ','CANCELLED')",
            name="ck_email_outbox_status",
        ),
    )
    op.create_index(
        "idx_email_outbox_pending",
        "email_outbox",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_email_outbox_status_created",
        "email_outbox",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index("idx_email_outbox_to_email", "email_outbox", ["to_email"])
    op.create_index(
        "idx_email_outbox_resource",
        "email_outbox",
        ["related_resource_type", "related_resource_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_email_outbox_resource", table_name="email_outbox")
    op.drop_index("idx_email_outbox_to_email", table_name="email_outbox")
    op.drop_index("idx_email_outbox_status_created", table_name="email_outbox")
    op.drop_index("idx_email_outbox_pending", table_name="email_outbox")
    op.drop_table("email_outbox")
