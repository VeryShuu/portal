"""Дроп реликтов парольной механики внешних учёток (passwordless).

Passwordless-вход вошёл в 113; на проде внешних учёток ещё не создавали,
поэтому парольные колонки и таблица токенов самовосстановления сносятся
сразу, без переходного окна:

- ``learning_accounts``: DROP COLUMN ``password_hash``, ``must_change_password``,
  ``failed_attempts``, ``locked_until`` — код-пути их не читали с 113;
- DROP TABLE ``learning_password_resets`` — новые токены не создаются с 113;
  грант роли исчезает вместе с таблицей.

Ревизии ниже 113 после этого даунгрейда/наката несовместимы (парольных
колонок нет) — откат релиза возможен только до состояния с 113.

Revision ID: 114
Revises: 113
Create Date: 2026-09-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "114"
down_revision: str | None = "113"
branch_labels = None
depends_on = None

ROLE = "learning_app"


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS learning_password_resets")
    op.execute("ALTER TABLE learning_accounts DROP COLUMN IF EXISTS password_hash")
    op.execute("ALTER TABLE learning_accounts DROP COLUMN IF EXISTS must_change_password")
    op.execute("ALTER TABLE learning_accounts DROP COLUMN IF EXISTS failed_attempts")
    op.execute("ALTER TABLE learning_accounts DROP COLUMN IF EXISTS locked_until")


def downgrade() -> None:
    # Восстановление структуры (данные паролей/токенов невосстановимы — они
    # были одноразовыми секретами); учётки 113+ получают NULL-хэши.
    op.execute("ALTER TABLE learning_accounts ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    op.execute(
        "ALTER TABLE learning_accounts ADD COLUMN IF NOT EXISTS must_change_password "
        "BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE learning_accounts ADD COLUMN IF NOT EXISTS failed_attempts "
        "INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE learning_accounts ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ")
    op.create_table(
        "learning_password_resets",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE learning_password_resets TO {ROLE}")
