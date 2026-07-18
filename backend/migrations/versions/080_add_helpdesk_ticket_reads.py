"""add helpdesk_ticket_reads (agent read-state marker table)

Revision ID: 080
Revises: 079
Create Date: 2026-07-18

Per-agent read-state marker для подсветки непрочитанных заявок в инбоксе агента
(«какие тикеты обновились за ночь, которые я ещё не открывал»).

Подход: одна строка на пару ``ticket_id`` × ``user_id`` с полем ``last_seen_at``
(timestamp последнего открытия карточки агентом). Тикет «непрочитан» для агента,
если существует публичное входящее сообщение (``direction='inbound'``,
``visibility='public'``) с ``created_at > COALESCE(last_seen_at, '-infinity')``.

Почему marker-таблица, а не колонка на тикете: тикет виден **многим** агентам,
у каждого своё «last seen» (аналог ``news_likes``, ``kb_article_feedback``).
По образцу Zammad/FreeScout (``conversation_user`` pivot), а не OTRS
(``ticket_flag`` per-article — таблица растёт O(сообщений×агентов), тут
это избыточно).

Backfill не нужен: отсутствующая строка = «никогда не видел», что логично
совпадает с дефолтом «непрочитан» для существующих тикетов (агенты увидят
подсветку на старых тикетах с inbound-public-сообщениями — это разумно: они их
действительно не открывали в этом UI).

Cleanup не нужен: одна строка на ticket×user, ``ON DELETE CASCADE`` на обеих
FK — при архивации/удалении тикета или аккаунта строки чистятся автоматически.

DDL написан вручную через ``op.execute`` (как 075-079): ``IF NOT EXISTS`` делает
миграцию идемпотентной, zero-downtime (новая таблица, без блокировок).
"""

from alembic import op

revision: str = "080"
down_revision: str | None = "079"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS helpdesk_ticket_reads (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id    UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Одна строка на пару ticket×user — UPSERT через ON CONFLICT по этому индексу.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_helpdesk_ticket_reads_ticket_user
            ON helpdesk_ticket_reads(ticket_id, user_id)
        """
    )
    # Lookup «все мои read-states» (для обогащения списка инбокса непрочитанностью).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_helpdesk_ticket_reads_user
            ON helpdesk_ticket_reads(user_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS helpdesk_ticket_reads CASCADE")
