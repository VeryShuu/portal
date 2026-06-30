"""add helpdesk module (tickets, messages, attachments, agents, email_log,
mailbox_settings, archive)

Revision ID: 075
Revises: 074
Create Date: 2026-06-30

Single authoritative source for the helpdesk schema. DDL is written by hand
through op.execute (not autogenerate): IDENTITY columns, table partitioning,
partial indexes and CHECK constraints are not handled correctly by autogenerate.
"""

from alembic import op

revision: str = "075"
down_revision: str | None = "074"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # --- helpdesk_tickets -------------------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_tickets (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            number              BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            subject             VARCHAR(500) NOT NULL,
            description         TEXT         NOT NULL,
            description_html    TEXT,
            status              VARCHAR(20)  NOT NULL DEFAULT 'new',
            source              VARCHAR(20)  NOT NULL,
            requester_user_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
            requester_email     VARCHAR(320) NOT NULL,
            requester_name      VARCHAR(255),
            assignee_user_id    UUID         REFERENCES users(id) ON DELETE SET NULL,
            assigned_at         TIMESTAMPTZ,
            closed_at           TIMESTAMPTZ,
            closed_by_user_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
            last_activity_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            references_archived_ticket_number BIGINT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_helpdesk_status
                CHECK (status IN ('new','open','pending','resolved','closed')),
            CONSTRAINT ck_helpdesk_source
                CHECK (source IN ('email','web'))
        )
        """
    )
    op.execute("CREATE INDEX ix_helpdesk_tickets_status ON helpdesk_tickets(status)")
    op.execute(
        """
        CREATE INDEX ix_helpdesk_tickets_assignee ON helpdesk_tickets(assignee_user_id)
            WHERE assignee_user_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_helpdesk_tickets_requester ON helpdesk_tickets(requester_user_id)
            WHERE requester_user_id IS NOT NULL
        """
    )
    op.execute("CREATE INDEX ix_helpdesk_tickets_email ON helpdesk_tickets(LOWER(requester_email))")
    op.execute(
        "CREATE INDEX ix_helpdesk_tickets_last_activity ON helpdesk_tickets(last_activity_at DESC)"
    )
    op.execute(
        """
        CREATE INDEX ix_helpdesk_tickets_open_list ON helpdesk_tickets(status, last_activity_at DESC)
            WHERE status IN ('new','open','pending')
        """
    )
    op.execute(
        """
        CREATE INDEX ix_helpdesk_tickets_ref_archive ON helpdesk_tickets(references_archived_ticket_number)
            WHERE references_archived_ticket_number IS NOT NULL
        """
    )

    # --- helpdesk_messages ------------------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id       UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
            author_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            author_email    VARCHAR(320) NOT NULL,
            author_name     VARCHAR(255),
            direction       VARCHAR(10)  NOT NULL,
            visibility      VARCHAR(10)  NOT NULL DEFAULT 'public',
            body_text       TEXT NOT NULL,
            body_html       TEXT,
            source          VARCHAR(20) NOT NULL,
            email_message_id VARCHAR(998),
            in_reply_to     VARCHAR(998),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_helpdesk_messages_direction
                CHECK (direction IN ('inbound','outbound')),
            CONSTRAINT ck_helpdesk_messages_visibility
                CHECK (visibility IN ('public','internal')),
            CONSTRAINT ck_helpdesk_messages_source
                CHECK (source IN ('email','web'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_helpdesk_messages_email_msg_id
            ON helpdesk_messages(email_message_id)
            WHERE email_message_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_helpdesk_messages_ticket ON helpdesk_messages(ticket_id, created_at)"
    )

    # --- helpdesk_attachments --------------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_attachments (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id    UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
            message_id   UUID REFERENCES helpdesk_messages(id) ON DELETE CASCADE,
            filename     VARCHAR(500) NOT NULL,
            content_type VARCHAR(255) NOT NULL,
            size_bytes   BIGINT       NOT NULL,
            storage_backend VARCHAR(20) NOT NULL DEFAULT 'nextcloud',
            storage_key  VARCHAR(1000) NOT NULL,
            uploaded_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_helpdesk_attachments_storage_backend
                CHECK (storage_backend IN ('nextcloud'))
        )
        """
    )
    op.execute("CREATE INDEX ix_helpdesk_attachments_ticket ON helpdesk_attachments(ticket_id)")
    op.execute("CREATE INDEX ix_helpdesk_attachments_message ON helpdesk_attachments(message_id)")

    # --- helpdesk_agents --------------------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_agents (
            user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            added_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notify_new  BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )

    # --- helpdesk_email_log ----------------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_email_log (
            message_id      VARCHAR(998) PRIMARY KEY,
            ticket_id       UUID REFERENCES helpdesk_tickets(id) ON DELETE SET NULL,
            message_db_id   UUID REFERENCES helpdesk_messages(id) ON DELETE SET NULL,
            received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status          VARCHAR(20) NOT NULL,
            error           TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_helpdesk_email_log_received ON helpdesk_email_log(received_at DESC)"
    )

    # --- helpdesk_mailbox_settings ---------------------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_mailbox_settings (
            id                    SMALLINT PRIMARY KEY DEFAULT 1,
            imap_host             VARCHAR(255) NOT NULL,
            imap_port             INTEGER      NOT NULL DEFAULT 993,
            imap_username         VARCHAR(255) NOT NULL,
            imap_password_enc     TEXT         NOT NULL,
            imap_use_ssl          BOOLEAN      NOT NULL DEFAULT TRUE,
            imap_folder           VARCHAR(255) NOT NULL DEFAULT 'INBOX',
            poll_interval_seconds INTEGER      NOT NULL DEFAULT 60,
            delete_after_fetch    BOOLEAN      NOT NULL DEFAULT FALSE,
            support_address       VARCHAR(320) NOT NULL,
            support_reply_to      VARCHAR(320),
            updated_by_user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_helpdesk_mailbox_singleton CHECK (id = 1),
            CONSTRAINT ck_helpdesk_mailbox_poll_interval
                CHECK (poll_interval_seconds BETWEEN 30 AND 600)
        )
        """
    )

    # --- helpdesk_tickets_archive (partitioned) --------------------------
    op.execute(
        """
        CREATE TABLE helpdesk_tickets_archive (
            id              UUID NOT NULL,
            number          BIGINT NOT NULL,
            subject         VARCHAR(500) NOT NULL,
            requester_email VARCHAR(320) NOT NULL,
            requester_user_id UUID,
            assignee_user_id  UUID,
            opened_at       TIMESTAMPTZ NOT NULL,
            closed_at       TIMESTAMPTZ NOT NULL,
            closed_by_user_id UUID,
            payload         JSONB NOT NULL,
            archived_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, closed_at)
        ) PARTITION BY RANGE (closed_at)
        """
    )

    # First monthly partition: current month.
    op.execute(
        """
        DO $$
        DECLARE
            start_date DATE := DATE_TRUNC('month', NOW())::DATE;
            end_date   DATE := (start_date + '1 month'::INTERVAL)::DATE;
            tbl_name   TEXT := 'helpdesk_tickets_archive_' || TO_CHAR(start_date, 'YYYY_MM');
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = tbl_name AND n.nspname = 'public'
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF helpdesk_tickets_archive '
                    'FOR VALUES FROM (%L) TO (%L)',
                    tbl_name, start_date, end_date
                );
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # Reverse dependency order: archive → mailbox → log → agents →
    # attachments → messages → tickets.
    op.execute("DROP TABLE IF EXISTS helpdesk_tickets_archive CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_mailbox_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_email_log CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_attachments CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS helpdesk_tickets CASCADE")
