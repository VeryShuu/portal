"""mailing recipients directory (news share-by-email address book)

Revision ID: 071
Revises: 070
Create Date: 2026-06-16

Curated address book of allowed recipients for the news "share by email"
feature (docs/wip/news-email-share.md). Editors pick recipients from this
directory; ad-hoc addresses are not allowed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "071"
down_revision: str | None = "070"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "mailing_recipients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_mailing_recipients_email_ci_active",
        "mailing_recipients",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_mailing_recipients_active",
        "mailing_recipients",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_mailing_recipients_active", table_name="mailing_recipients")
    op.drop_index("idx_mailing_recipients_email_ci_active", table_name="mailing_recipients")
    op.drop_table("mailing_recipients")
