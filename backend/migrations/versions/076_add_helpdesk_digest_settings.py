"""add helpdesk_digest_settings (singleton for daily digest schedule)

Revision ID: 076
Revises: 075
Create Date: 2026-07-01

Singleton table for the daily digest email schedule (hour/minute/weekdays,
enabled flag). Seed row is inserted immediately — unlike ``helpdesk_mailbox_settings``
there is no NOT NULL column without a DEFAULT, so the row exists from the start
and the digest worker / Admin API always find it. DDL is hand-written through
``op.execute`` (consistent with 075: CHECK constraints + singleton guard).
"""

from alembic import op

revision: str = "076"
down_revision: str | None = "075"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE helpdesk_digest_settings (
            id                  SMALLINT PRIMARY KEY DEFAULT 1,
            enabled             BOOLEAN      NOT NULL DEFAULT TRUE,
            digest_hour         SMALLINT     NOT NULL DEFAULT 8,
            digest_minute       SMALLINT     NOT NULL DEFAULT 0,
            digest_schedule     VARCHAR(16)  NOT NULL DEFAULT 'weekdays',
            updated_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_helpdesk_digest_singleton CHECK (id = 1),
            CONSTRAINT ck_helpdesk_digest_hour CHECK (digest_hour BETWEEN 0 AND 23),
            CONSTRAINT ck_helpdesk_digest_minute CHECK (digest_minute BETWEEN 0 AND 59),
            CONSTRAINT ck_helpdesk_digest_schedule
                CHECK (digest_schedule IN ('weekdays', 'daily'))
        )
        """
    )
    # Seed the singleton row immediately (no NOT NULL columns block the insert).
    op.execute("INSERT INTO helpdesk_digest_settings (id) VALUES (1)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS helpdesk_digest_settings CASCADE")
