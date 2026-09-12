"""Add partial indexes on deleted_at IS NULL for soft-delete tables

Revision ID: 045
Revises: 044
Create Date: 2026-05-17

Adds partial indexes (WHERE deleted_at IS NULL) to tables that were missing them:
  - news: idx_news_active (status, publish_at)
  - photo_folders: idx_photo_folders_active (parent_id)
  - photos: idx_photos_active (folder_id)
  - kb_article_comments: idx_kb_comments_active (article_id)

Runs inside the regular alembic transaction. CREATE INDEX briefly takes a
SHARE lock on the table (blocks writes, allows reads) for the duration of the
build; acceptable on small databases. IF NOT EXISTS makes the migration
idempotent in case an index was created out-of-band beforehand.
"""

from alembic import op

revision: str = "045"
down_revision: str | None = "044"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_news_active "
        "ON news (status, publish_at) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photo_folders_active "
        "ON photo_folders (parent_id) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photos_active "
        "ON photos (folder_id) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_comments_active "
        "ON kb_article_comments (article_id) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_kb_comments_active")
    op.execute("DROP INDEX IF EXISTS idx_photos_active")
    op.execute("DROP INDEX IF EXISTS idx_photo_folders_active")
    op.execute("DROP INDEX IF EXISTS idx_news_active")
