"""drop helpdesk_messages.visibility — internal notes feature removed

Revision ID: 084
Revises: 083
Create Date: 2026-07-22

Решение владельца: функционал «Внутренняя заметка» (``visibility='internal'``)
удалён — не используется. Все сообщения тикета публичные, колонка
``helpdesk_messages.visibility`` и enum ``HelpdeskVisibility`` убраны из кода.

На момент миграции в проде ``internal``-сообщений нет (проверено), поэтому
data-migration не требуется — просто DROP COLUMN с CHECK-констрейнтом.

DDL через ``op.execute`` (консистентно с миграциями 075/079 — hand-written).
``IF EXISTS`` на DROP — идемпотентность при повторном apply.
"""

from alembic import op

revision: str = "084"
down_revision: str | None = "083"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # CHECK-констрейнт сначала (он ссылается на колонку), затем сама колонка.
    op.execute(
        "ALTER TABLE helpdesk_messages DROP CONSTRAINT IF EXISTS ck_helpdesk_messages_visibility"
    )
    op.execute("ALTER TABLE helpdesk_messages DROP COLUMN IF EXISTS visibility")


def downgrade() -> None:
    # Возврат колонки + CHECK (default 'public'). Исторические internal-значения
    # не восстанавливаем — данных нет, а обратная data-mig неоднозначна.
    op.execute(
        "ALTER TABLE helpdesk_messages ADD COLUMN visibility VARCHAR(10) NOT NULL DEFAULT 'public'"
    )
    op.execute(
        "ALTER TABLE helpdesk_messages ADD CONSTRAINT ck_helpdesk_messages_visibility "
        "CHECK (visibility IN ('public','internal'))"
    )
