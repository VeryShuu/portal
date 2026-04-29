"""add indexes for FK columns used by filters and joins

Revision ID: 022
Revises: 021
Create Date: 2026-04-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_versions_editor_id ON news_versions(editor_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_links_created_by ON service_links(created_by)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_sections_created_by ON kb_sections(created_by)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_article_comments_author_id ON kb_article_comments(author_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_suggestions_author_id ON kb_suggestions(author_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_suggestions_reviewed_by ON kb_suggestions(reviewed_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photo_folders_cover_photo_id ON photo_folders(cover_photo_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_photos_uploaded_by ON photos(uploaded_by)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_photo_share_tokens_created_by ON photo_share_tokens(created_by)"
    )


def downgrade() -> None:
    for idx in [
        "idx_news_versions_editor_id",
        "idx_service_links_created_by",
        "idx_kb_sections_created_by",
        "idx_kb_article_comments_author_id",
        "idx_kb_suggestions_author_id",
        "idx_kb_suggestions_reviewed_by",
        "idx_photo_folders_cover_photo_id",
        "idx_photos_uploaded_by",
        "idx_photo_share_tokens_created_by",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
