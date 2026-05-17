"""users email partial unique index (active users only)

Revision ID: 037
Revises: 036
Create Date: 2026-05-05
"""


from alembic import op

revision: str = "037"
down_revision: str | None = "036"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction block (Alembic wraps each
    # migration in one). Since migrations run at deploy time with no concurrent
    # writers, a regular CREATE UNIQUE INDEX is safe here.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_ci_active "
        "ON users (lower(email)) WHERE deleted_at IS NULL"
    )
    op.execute("DROP INDEX IF EXISTS idx_users_email_ci")


def downgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_ci "
        "ON users (lower(email)) WHERE deleted_at IS NULL"
    )
    op.execute("DROP INDEX IF EXISTS idx_users_email_ci_active")
