"""add indexes for FK columns used by filters and joins

Revision ID: 022
Revises: 021
Create Date: 2026-04-27
"""

from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_INDEXES: list[tuple[str, str]] = [
    ("idx_news_versions_editor_id", "news_versions(editor_id)"),
    ("idx_service_links_created_by", "service_links(created_by)"),
    ("idx_kb_sections_created_by", "kb_sections(created_by)"),
    ("idx_kb_article_comments_author_id", "kb_article_comments(author_id)"),
    ("idx_kb_suggestions_author_id", "kb_suggestions(author_id)"),
    ("idx_kb_suggestions_reviewed_by", "kb_suggestions(reviewed_by)"),
    ("idx_photo_folders_cover_photo_id", "photo_folders(cover_photo_id)"),
    ("idx_photos_uploaded_by", "photos(uploaded_by)"),
    ("idx_photo_share_tokens_created_by", "photo_share_tokens(created_by)"),
]


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY must run outside a transaction.
    # autocommit_block() temporarily exits the migration transaction
    # in a way that survives any Alembic execution mode.
    with op.get_context().autocommit_block():
        for name, target in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _ in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
