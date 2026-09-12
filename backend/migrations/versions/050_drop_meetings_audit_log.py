"""drop meetings_audit_log table (audit goes to shared audit_log)

Revision ID: 050
Revises: 049
Create Date: 2026-05-18
"""

from alembic import op

revision: str = "050"
down_revision: str | None = "049"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meetings_audit_log CASCADE")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS meetings_audit_log (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            action         VARCHAR(64) NOT NULL,
            user_id        UUID,
            username       VARCHAR(255),
            user_email     VARCHAR(320),
            user_role      VARCHAR(32),
            resource_type  VARCHAR(32),
            resource_id    UUID,
            resource_title VARCHAR(500),
            details        JSONB,
            ip_address     INET,
            user_agent     TEXT,
            timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_audit_timestamp "
        "ON meetings_audit_log (timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_audit_action_ts "
        "ON meetings_audit_log (action, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_audit_user_ts "
        "ON meetings_audit_log (user_id, timestamp DESC)"
    )
