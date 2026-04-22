"""Consolidate news FTS column: drop unused body_tsvector Text, rename body_tsv -> body_tsvector

Revision ID: 007
Revises: 006
Create Date: 2026-04-22

P0-9 fix: previously migration 002 created two columns:
  * body_tsvector TEXT (NULL, unused, model referenced this name)
  * body_tsv tsvector GENERATED (the real FTS column with idx_news_fts index)

The model's `body_tsvector` field never matched the actual generated column,
so SQLAlchemy-emitted FTS queries silently returned wrong results. This
migration drops the dead Text column and renames the generated column to
`body_tsvector` (matching the model). The GIN index is recreated on the
renamed column.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_news_fts", table_name="news")
    op.execute("ALTER TABLE news DROP COLUMN IF EXISTS body_tsvector")
    op.execute("ALTER TABLE news RENAME COLUMN body_tsv TO body_tsvector")
    op.create_index("idx_news_fts", "news", ["body_tsvector"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_news_fts", table_name="news")
    op.execute("ALTER TABLE news RENAME COLUMN body_tsvector TO body_tsv")
    op.execute("ALTER TABLE news ADD COLUMN body_tsvector TEXT")
    op.create_index("idx_news_fts", "news", ["body_tsv"], postgresql_using="gin")
