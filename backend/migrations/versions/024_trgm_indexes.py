"""add trigram indexes for ILIKE search on users.full_name and service_links.title

Revision ID: 024
Revises: 023
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_full_name_trgm "
        "ON users USING gin (full_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_department_trgm "
        "ON users USING gin (department gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_service_links_title_trgm "
        "ON service_links USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_service_links_url_trgm "
        "ON service_links USING gin (url gin_trgm_ops)"
    )


def downgrade() -> None:
    for idx in [
        "idx_users_full_name_trgm",
        "idx_users_department_trgm",
        "idx_service_links_title_trgm",
        "idx_service_links_url_trgm",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
