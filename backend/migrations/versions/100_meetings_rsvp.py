"""meetings RSVP: приём ответов на приглашения через почту портала

Revision ID: 100
Revises: 099
Create Date: 2026-08-20

Хранение статусов участия (Accept/Decline/Tentative из IMIP-ответов Outlook
и других клиентов, которые участники шлют на ORGANIZER = адрес портала):

1. ``meeting_rsvp`` — upsert-таблица статусов: ключ
   ``(booking_id, participant_email)`` (повторный ответ перезаписывает статус),
   ``status ∈ ('accepted','declined','tentative')`` (CHECK),
   ``participant_user_id`` nullable (внешние участники — только email).
   Индекс по ``updated_at`` — окно 30-минутного дайджеста организатору.

2. ``meeting_rsvp_email_log`` — дедуп обработанных писем по ``Message-ID``.
   Ящик portal@ общий (люди читают его руками; параллельно поллится
   ERP-синком), поэтому «обработано» нельзя определять почтовыми флагами —
   тот же паттерн, что ``erp_sync_runs.message_id`` / ``helpdesk_email_log``.

3. ``meeting_bookings.rsvp_final_digest_sent_at`` — идемпотентность финальной
   сводки «весь список приглашённых со статусами» за 15 минут до встречи
   (NULL = ещё не отправлена).

DDL вручную через ``op.execute`` (как 081-099): zero-downtime — новые
таблицы/индексы, nullable-колонка в существующей таблице.
"""

from alembic import op

revision: str = "100"
down_revision: str | None = "099"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_rsvp (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            booking_id          UUID NOT NULL REFERENCES meeting_bookings(id) ON DELETE CASCADE,
            participant_email   VARCHAR(320) NOT NULL,
            participant_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            status              VARCHAR(16) NOT NULL,
            source              VARCHAR(16) NOT NULL DEFAULT 'email',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_meeting_rsvp_status
                CHECK (status IN ('accepted', 'declined', 'tentative')),
            CONSTRAINT uq_meeting_rsvp_booking_participant
                UNIQUE (booking_id, participant_email)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_meeting_rsvp_booking ON meeting_rsvp (booking_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_meeting_rsvp_updated ON meeting_rsvp (updated_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_rsvp_email_log (
            message_id      VARCHAR(998) PRIMARY KEY,
            processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        ALTER TABLE meeting_bookings
        ADD COLUMN IF NOT EXISTS rsvp_final_digest_sent_at TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE meeting_bookings DROP COLUMN IF EXISTS rsvp_final_digest_sent_at")
    op.execute("DROP TABLE IF EXISTS meeting_rsvp_email_log")
    op.execute("DROP INDEX IF EXISTS idx_meeting_rsvp_updated")
    op.execute("DROP INDEX IF EXISTS idx_meeting_rsvp_booking")
    op.execute("DROP TABLE IF EXISTS meeting_rsvp")
