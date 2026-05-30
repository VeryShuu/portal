"""Switch news FTS from 'russian' to 'russian_hunspell'

Revision ID: 011
Revises: 010
Create Date: 2026-04-23

Pre-Phase-4 review P0-1 (DB): the news.body_tsvector generated column was
created in migration 002 with the built-in `russian` snowball stemmer while
the rest of the portal (KB articles, search) uses the hunspell-backed
`russian_hunspell` configuration set up in init.sql. This produces noticeably
worse recall on inflected words and divergent search results between modules.

The fix recreates the generated tsvector column with the hunspell config and
rebuilds the GIN index. Existing rows are recomputed automatically because
GENERATED ALWAYS AS columns are recalculated on rewrite.
"""

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("DROP INDEX IF EXISTS idx_news_fts")
    op.execute("ALTER TABLE news DROP COLUMN body_tsvector")
    op.execute(
        """
        ALTER TABLE news
        ADD COLUMN body_tsvector tsvector
            GENERATED ALWAYS AS (
                to_tsvector(
                    'russian_hunspell',
                    coalesce(title, '') || ' ' || coalesce(body, '')
                )
            ) STORED
        """
    )
    op.execute("CREATE INDEX idx_news_fts ON news USING gin (body_tsvector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_news_fts")
    op.execute("ALTER TABLE news DROP COLUMN body_tsvector")
    op.execute(
        """
        ALTER TABLE news
        ADD COLUMN body_tsvector tsvector
            GENERATED ALWAYS AS (
                to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(body, ''))
            ) STORED
        """
    )
    op.execute("CREATE INDEX idx_news_fts ON news USING gin (body_tsvector)")
