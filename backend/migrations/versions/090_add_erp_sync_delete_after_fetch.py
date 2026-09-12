"""add erp_sync_settings.delete_after_fetch (удаление писем после забора)

Revision ID: 090
Revises: 089
Create Date: 2026-08-01

Additive ``ALTER TABLE`` (zero-downtime): новое поле ``delete_after_fetch``
``BOOL NOT NULL DEFAULT FALSE``. Включает физическое удаление писем из общего
IMAP-ящика после успешного импорта (``STORE +FLAGS \\Deleted`` + ``EXPUNGE``),
клон паттерна ``helpdesk_mailbox_settings.delete_after_fetch``.

Default ``FALSE`` — удаление писем на общем ящике необратимо, пусть админ
осознанно включит его в админке. Дедуп по ``erp_sync_runs.message_id`` (UNIQUE)
защищает от повторной обработки и без удаления.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "090"
down_revision: str | None = "089"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        # nosec B608 — статический DDL без интерполяции.
        text(
            "ALTER TABLE erp_sync_settings "
            "ADD COLUMN IF NOT EXISTS delete_after_fetch BOOL "
            "NOT NULL DEFAULT FALSE"
        )
    )


def downgrade() -> None:
    op.execute(
        # nosec B608 — статический DDL без интерполяции.
        text("ALTER TABLE erp_sync_settings DROP COLUMN IF EXISTS delete_after_fetch")
    )
