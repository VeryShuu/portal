"""add helpdesk_attachments.is_inline + content_id (inline images in email-ingress)

Revision ID: 077
Revises: 076
Create Date: 2026-07-16

Schema-drift фикс: колонки ``is_inline`` и ``content_id`` были добавлены в ORM-модель
``HelpdeskAttachment`` (для inline-картинок в email-ingress, см. ``email_images.py``)
в коммите 24a15bd, но миграция для БД не была создана → любой запрос с
``selectinload(HelpdeskMessage.attachments)`` падал с
``UndefinedColumnError: column helpdesk_attachments.is_inline does not exist``
(500 на ``GET /api/v1/helpdesk/tickets`` и ``/tickets/{id}``).

Колонки nullable-safe:
* ``is_inline`` — Boolean NOT NULL DEFAULT FALSE (zero-downtime: DEFAULT заполняет
  существующие строки сразу, NOT NULL безопасен т.к. есть DEFAULT).
* ``content_id`` — String(320) NULL (Content-ID inline-картинки; пуст для обычных
  вложений).

DDL через ``op.execute`` (консистентно с миграцией 075 — hand-written, не autogenerate).
"""

from alembic import op

revision: str = "077"
down_revision: str | None = "076"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # is_inline: NOT NULL DEFAULT FALSE — zero-downtime (DEFAULT backfill'ит
    # существующие строки атомарно при ADD COLUMN). Все текущие вложения —
    # обычные (is_inline=false), inline-картинки появятся только в новых письмах.
    op.execute(
        "ALTER TABLE helpdesk_attachments "
        "ADD COLUMN IF NOT EXISTS is_inline BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE helpdesk_attachments ADD COLUMN IF NOT EXISTS content_id VARCHAR(320)")


def downgrade() -> None:
    op.execute("ALTER TABLE helpdesk_attachments DROP COLUMN IF EXISTS content_id")
    op.execute("ALTER TABLE helpdesk_attachments DROP COLUMN IF EXISTS is_inline")
