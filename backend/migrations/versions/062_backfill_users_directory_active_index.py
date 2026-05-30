"""
Revision ID: 062
Revises: 061
Create Date: 2026-05-28

Backfill idx_users_directory_active that migration 046 was supposed to create.

Migration 046 originally tried to create idx_users_active (department, full_name)
WHERE deleted_at IS NULL via CREATE INDEX IF NOT EXISTS, but the name collided
with idx_users_active (email) from migration 028, so the directory index was
silently skipped on every environment where 028 had already run.

046 has since been renamed to use idx_users_directory_active, but environments
that already advanced past 046 will not re-run it. This migration creates the
missing index everywhere — both fresh databases (no-op due to IF NOT EXISTS,
since the renamed 046 already created it) and existing deployments.
"""

from alembic import op

revision: str = "062"
down_revision: str | None = "061"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_directory_active "
        "ON users (department, full_name) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_directory_active")
