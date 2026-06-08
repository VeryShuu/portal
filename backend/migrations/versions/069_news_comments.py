"""news comments

Revision ID: 069
Revises: 068
Create Date: 2026-06-08

Adds the ``news_comments`` table (flat list, soft-delete via ``deleted_at`` —
mirror of ``kb_article_comments``) and a denormalised ``news.comment_count``
counter (active comments only) maintained in the same transaction as the
create/delete mutation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "069"
down_revision: str | None = "068"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "news_comments",
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
        ),
        sa.Column(
            "author_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "idx_news_comments_news", "news_comments", ["news_id", "created_at"]
    )
    op.create_index(
        "idx_news_comments_active",
        "news_comments",
        ["news_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_news_comments_active", table_name="news_comments")
    op.drop_index("idx_news_comments_news", table_name="news_comments")
    op.drop_table("news_comments")
    op.drop_column("news", "comment_count")
