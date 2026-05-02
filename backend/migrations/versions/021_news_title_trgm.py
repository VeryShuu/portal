"""news.title trgm + photo_folders.fs_path indexes

Revision ID: 021
Revises: 020
Create Date: 2026-04-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_title_trgm ON news USING GIN (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_photo_folders_fs_path ON photo_folders(fs_path)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_photo_folders_fs_path")
    op.execute("DROP INDEX IF EXISTS idx_news_title_trgm")
