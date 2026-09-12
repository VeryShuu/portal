"""Add news polls tables

Revision ID: 053
Revises: 052
Create Date: 2026-05-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "053"
down_revision: str | None = "052"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. news_polls
    op.create_table(
        "news_polls",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "news_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("is_multiple", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_choices", sa.Integer(), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_revote", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "results_visibility",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'after_vote'"),
        ),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "results_visibility IN ('always','after_vote','after_close','only_admin_editor')",
            name="ck_news_polls_results_visibility",
        ),
        sa.CheckConstraint(
            "max_choices IS NULL OR (is_multiple = true AND max_choices >= 1)",
            name="ck_news_polls_max_choices",
        ),
    )

    # 2. news_poll_options
    op.create_table(
        "news_poll_options",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "poll_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_polls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=200), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("votes_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "text IS NOT NULL OR image_url IS NOT NULL",
            name="ck_news_poll_options_text_or_image",
        ),
    )
    op.create_index(
        "idx_poll_options_poll_id_sort",
        "news_poll_options",
        ["poll_id", "sort_order"],
    )

    # 3. news_poll_voters
    op.create_table(
        "news_poll_voters",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "poll_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_polls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("poll_id", "user_id", name="uq_news_poll_voters_poll_user"),
    )
    op.create_index("idx_news_poll_voters_user_id", "news_poll_voters", ["user_id"])

    # 4. news_poll_votes
    op.create_table(
        "news_poll_votes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "poll_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_polls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "voter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_poll_voters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "option_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_poll_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("option_id", "voter_id", name="uq_news_poll_votes_option_voter"),
    )
    op.create_index(
        "idx_news_poll_votes_poll_id_option_id",
        "news_poll_votes",
        ["poll_id", "option_id"],
    )


def downgrade() -> None:
    op.drop_table("news_poll_votes")
    op.drop_table("news_poll_voters")
    op.drop_table("news_poll_options")
    op.drop_table("news_polls")
