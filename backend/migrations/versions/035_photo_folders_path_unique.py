"""photo_folders.path: add UNIQUE constraint

ADR-031 specifies that `path` is a materialized slash-separated slug path and
must be unique globally.  The original migration created only a regular index
(idx_photo_folders_path), leaving room for duplicate paths under concurrent
renames.  This migration replaces that index with a UNIQUE partial index
(WHERE deleted_at IS NULL) — soft-deleted rows are excluded.

Revision ID: 035
Revises: 034
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction block (Alembic wraps each
    # migration in one).  Since migrations run at deploy time with no concurrent
    # writers, a regular CREATE UNIQUE INDEX is safe here.
    op.execute("DROP INDEX IF EXISTS idx_photo_folders_path")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_photo_folders_path "
        "ON photo_folders (path) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_photo_folders_path")
    op.create_index("idx_photo_folders_path", "photo_folders", ["path"])
