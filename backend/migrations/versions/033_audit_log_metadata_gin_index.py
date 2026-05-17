"""Add GIN index on audit_log.metadata for efficient JSONB filtering.

Revision ID: 033
Revises: 032
Create Date: 2026-05-04

Without a GIN index, filtering audit_log by metadata fields (e.g.,
metadata->>'resource_type') requires a full-scan of every partition.
NOTE: CREATE INDEX CONCURRENTLY is NOT supported on partitioned tables
(PostgreSQL limitation), so we use a regular CREATE INDEX.
IF NOT EXISTS guards idempotency.
"""


from alembic import op

revision: str = "033"
down_revision: str | None = "032"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "idx_audit_log_metadata_gin ON audit_log USING gin(metadata jsonb_path_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_log_metadata_gin")
