"""news and news_versions tables

Revision ID: 002
Revises: 001
Create Date: 2026-04-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_tsvector", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("target_departments", ARRAY(sa.String()), nullable=True),
        sa.Column("target_roles", ARRAY(sa.String()), nullable=True),
        sa.Column("author_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("publish_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("archive_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_news_status"),
    )

    op.execute("""
        ALTER TABLE news
        ADD COLUMN body_tsv tsvector
            GENERATED ALWAYS AS (
                to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(body, ''))
            ) STORED
    """)

    op.create_index("idx_news_status_published_at", "news", ["status", "publish_at"])
    op.create_index("idx_news_author", "news", ["author_id"])
    op.create_index("idx_news_fts", "news", ["body_tsv"], postgresql_using="gin")
    op.create_index("idx_news_deleted", "news", ["deleted_at"])

    op.create_table(
        "news_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("news_id", UUID(as_uuid=True),
                  sa.ForeignKey("news.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("editor_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_news_versions_news_id", "news_versions", ["news_id"])


def downgrade() -> None:
    op.drop_table("news_versions")
    op.drop_table("news")
