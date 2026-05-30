"""
Revision ID: 061
Revises: 060
Create Date: 2026-05-28

Composite indexes for kb_articles list_articles query (P3-1).

Filters: deleted_at IS NULL + status + optional created_by.
Sort: updated_at DESC.
"""

from alembic import op

revision: str = "061"
down_revision: str | None = "060"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_kb_articles_status_updated",
        "kb_articles",
        ["status", "updated_at"],
        postgresql_where="deleted_at IS NULL",
        postgresql_ops={"updated_at": "DESC"},
    )
    op.create_index(
        "idx_kb_articles_created_by_updated",
        "kb_articles",
        ["created_by", "updated_at"],
        postgresql_where="deleted_at IS NULL",
        postgresql_ops={"updated_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("idx_kb_articles_created_by_updated", table_name="kb_articles")
    op.drop_index("idx_kb_articles_status_updated", table_name="kb_articles")
