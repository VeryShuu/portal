"""Add missing partial indexes on deleted_at IS NULL for kb_sections, kb_articles, users

Revision ID: 046
Revises: 045
Create Date: 2026-05-17

Audit result: migration 045 covered news / photo_folders / photos /
kb_article_comments; migration 020 covered file_folders; migration 038
covered file_items.  Three tables were still missing partial indexes:

  - kb_sections: idx_kb_sections_active (parent_id)
      All tree-traversal and listing queries filter deleted_at IS NULL;
      without a partial index Postgres scans the full table.

  - kb_articles: idx_kb_articles_active (section_id)
      Every section page loads articles filtered by section_id + deleted_at IS NULL.
      Index was declared in the ORM __table_args__ but never created in a migration.
      Note: the ORM model previously included `deleted_at` as an indexed column
      alongside the WHERE condition — that column is always NULL inside the partial
      index and wastes storage.  Migration creates the clean (section_id)-only form
      and the model is updated to match.

  - users: idx_users_active (department, full_name)
      Admin user listing and the directory's alphabetical-within-department sort
      both filter deleted_at IS NULL; existing indexes (email CI unique, keycloak,
      staff_sort_order) do not cover the general listing path.

All three indexes use IF NOT EXISTS for idempotency.  They run inside the
regular Alembic transaction which takes a ShareLock for the index build
duration; acceptable for current data volumes.
"""


from alembic import op

revision: str = "046"
down_revision: str | None = "045"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_sections_active "
        "ON kb_sections (parent_id) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_articles_active "
        "ON kb_articles (section_id) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_active "
        "ON users (department, full_name) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_active")
    op.execute("DROP INDEX IF EXISTS idx_kb_articles_active")
    op.execute("DROP INDEX IF EXISTS idx_kb_sections_active")
