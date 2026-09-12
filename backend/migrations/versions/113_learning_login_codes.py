"""Вход внешних обучаемых по одноразовому коду из письма (passwordless).

Пароли учёток упраздняются: вместо ``/auth/learning/login`` с паролем —
двухшаговый вход (email → код из письма → verify). Код хранится только
хэшем (SHA-256), живёт минуты, одноразовый, ограничен числом попыток.

``learning_accounts.password_hash`` становится nullable — новые учётки
создаются без пароля. Существующие хэши сознательно НЕ обнуляются: при
откате релиза старый образ продолжает аутентифицировать старые учётки.
Физический дроп ``password_hash``/``must_change_password``/
``failed_attempts``/``locked_until`` и таблицы ``learning_password_resets``
— отдельная миграция 114 после устаканивания релиза.

Новые learning-миграции обязаны сами GRANT'ить роль (см. шапку 102).

Revision ID: 113
Revises: 112
Create Date: 2026-09-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "113"
down_revision: str | None = "112"
branch_labels = None
depends_on = None

ROLE = "learning_app"


def upgrade() -> None:
    op.create_table(
        "learning_login_codes",
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
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Активный код учётки: инвалидация предыдущих и lookup при verify.
    op.create_index(
        "ix_learning_login_codes_account",
        "learning_login_codes",
        ["account_id"],
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE learning_login_codes TO {ROLE}")
    op.execute("ALTER TABLE learning_accounts ALTER COLUMN password_hash DROP NOT NULL")


def downgrade() -> None:
    # Учётки, созданные после апгрейда без пароля, NOT NULL не пройдёт —
    # даунгрейд возможен только на данных, где все хэши заполнены.
    op.execute("ALTER TABLE learning_accounts ALTER COLUMN password_hash SET NOT NULL")
    op.drop_table("learning_login_codes")
