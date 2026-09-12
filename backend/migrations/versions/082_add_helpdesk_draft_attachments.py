"""add helpdesk_draft_attachments (inline-картинки в форме создания заявки)

Revision ID: 082
Revises: 081
Create Date: 2026-07-22

Temporary-attachment table для inline-картинок rich-редактора при **создании**
заявки — когда ``ticket_id`` ещё не существует (курица-яйца: inline-media
endpoint ``POST /tickets/{id}/inline-media`` требует ``ticket_id``).

Флоу:
1. Юзер вставляет картинку в ``TicketCreateModal`` → ``POST /draft-attachments``
   (без ticket_id) → файл льётся в ``/data/helpdesk/drafts/usr-{user_id}/``,
   строка в ``helpdesk_draft_attachments``.
2. ``<img src="/api/v1/helpdesk/draft-attachments/{id}">`` в ``description_html``.
3. На ``create_ticket``: ``backfill_draft_images`` переносит файлы в постоянное
   хранилище ``TKT-{number}/inline/``, переписывает ``src`` на
   ``/tickets/{id}/inline-media/{name}``, удаляет draft-строки (атомарно в той
   же транзакции, что и создание тикета).
4. Cron ``cleanup_expired_drafts`` (``worker/tasks/helpdesk.py``) удаляет строки
   + файлы старше ``HELPDESK_DRAFT_TTL_HOURS`` (orphan-черновики — юзер закрыл
   вкладку, не отправив заявку).

ACL детерминирована через ``uploaded_by_user_id`` (только владелец видит/serve).
``ON DELETE CASCADE`` на FK users — при удалении аккаунта draft'ы уходят автоматом.

DDL написан вручную через ``op.execute`` (как 075-081): ``IF NOT EXISTS`` делает
миграцию идемпотентной, zero-downtime (новая таблица, без блокировок).
"""

from alembic import op

revision: str = "082"
down_revision: str | None = "081"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS helpdesk_draft_attachments (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            uploaded_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename            VARCHAR(500) NOT NULL,
            original_name       VARCHAR(500) NOT NULL,
            content_type        VARCHAR(255) NOT NULL,
            size_bytes          BIGINT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Лимит-проверка и cleanup по user'у: «сколько активных draft'ов у юзера».
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_helpdesk_draft_attachments_user
            ON helpdesk_draft_attachments(uploaded_by_user_id)
        """
    )
    # Cron-cleanup: ``WHERE created_at < NOW() - TTL`` сканирует этот индекс.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_helpdesk_draft_attachments_created
            ON helpdesk_draft_attachments(created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS helpdesk_draft_attachments CASCADE")
