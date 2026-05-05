"""create audit_log partitioned table

Revision ID: 013
Revises: 012
Create Date: 2026-04-23

This migration is the single authoritative source for the audit_log schema.
init.sql previously duplicated this DDL; it has been removed from init.sql.
IF NOT EXISTS guards preserve compatibility with deployments where init.sql
already created the table before this migration existed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id             BIGSERIAL,
            event_type     VARCHAR(50)  NOT NULL,
            user_id        UUID,
            user_email     VARCHAR(255),
            resource_type  VARCHAR(50),
            resource_id    VARCHAR(255),
            resource_title VARCHAR(500),
            ip_address     INET,
            user_agent     TEXT,
            metadata       JSONB        NOT NULL DEFAULT '{}',
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_user_time
            ON audit_log(user_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_event_time
            ON audit_log(event_type, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_resource
            ON audit_log(resource_type, resource_id)
    """)

    op.execute("""
        DO $$
        DECLARE
            start_date DATE;
            end_date   DATE;
            tbl_name   TEXT;
        BEGIN
            FOR i IN 0..2 LOOP
                start_date := DATE_TRUNC('month', NOW()) + (i || ' month')::INTERVAL;
                end_date   := start_date + '1 month'::INTERVAL;
                tbl_name   := 'audit_log_' || TO_CHAR(start_date, 'YYYY_MM');

                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = tbl_name AND n.nspname = 'public'
                ) THEN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
                        tbl_name,
                        start_date,
                        end_date
                    );
                END IF;
            END LOOP;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
