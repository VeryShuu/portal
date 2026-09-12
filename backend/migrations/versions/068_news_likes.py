"""news: likes (reactions)

Revision ID: 068
Revises: 067
Create Date: 2026-06-08

Adds the ``news_likes`` join table (one row per user per news, hard-delete
toggle like ``news_poll_voters``) and a denormalised ``news.like_count`` counter
maintained in the same transaction as the like/unlike mutation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "068"
down_revision: str | None = "067"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column("like_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "news_likes",
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
        sa.UniqueConstraint("news_id", "user_id", name="uq_news_likes_news_user"),
    )
    op.create_index("idx_news_likes_user", "news_likes", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_news_likes_user", table_name="news_likes")
    op.drop_table("news_likes")
    op.drop_column("news", "like_count")
