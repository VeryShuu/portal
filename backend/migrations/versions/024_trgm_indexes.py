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


_INDEXES: list[tuple[str, str]] = [
    ("idx_users_full_name_trgm", "users USING gin (full_name gin_trgm_ops)"),
    ("idx_users_department_trgm", "users USING gin (department gin_trgm_ops)"),
    ("idx_service_links_title_trgm", "service_links USING gin (title gin_trgm_ops)"),
    ("idx_service_links_url_trgm", "service_links USING gin (url gin_trgm_ops)"),
]


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY must run outside a transaction.
    with op.get_context().autocommit_block():
        for name, target in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _ in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
