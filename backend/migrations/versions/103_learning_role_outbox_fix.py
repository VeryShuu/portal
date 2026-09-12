"""Фиксы прод-контура DB-роли learning_app (ревью 2026-08-28).

Revision ID: 103
Revises: 102
Create Date: 2026-08-28

1. ``enqueue_outbox_email`` вставляет письмо через ``INSERT ... RETURNING id``:
   PostgreSQL требует SELECT на возвращаемую колонку, а миграция 102 выдала
   роли только INSERT на email_outbox — все learning-письма на проде падали бы
   с permission denied. Выдаём точечный column-grant ``SELECT (id)``: полный
   SELECT давать нельзя — в письмах outbox живут временные пароли (§5.2 ТЗ).
2. Снапшот личности участника в ``learning_course_participants``
   (display_name, email): зачисление и отчёт прогресса больше не читают
   ``users`` под ограниченной ролью (SELECT чужих таблиц learning_app
   недоступен по замыслу §10.8). Бэкфилл существующих строк из users и
   learning_accounts; далее снапшот пишется при зачислении.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "103"
down_revision: str | None = "102"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROLE = "learning_app"


def upgrade() -> None:
    # RETURNING id без полного SELECT: column-grant только на id.
    op.execute(f"GRANT SELECT (id) ON TABLE email_outbox TO {ROLE}")

    op.add_column(
        "learning_course_participants",
        sa.Column("display_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "learning_course_participants",
        sa.Column("email", sa.String(255), nullable=True),
    )
    op.execute(
        """
        UPDATE learning_course_participants p
        SET display_name = u.full_name, email = u.email
        FROM users u
        WHERE p.user_id = u.id AND (p.display_name IS NULL OR p.email IS NULL)
        """
    )
    op.execute(
        """
        UPDATE learning_course_participants p
        SET display_name = a.full_name, email = a.email
        FROM learning_accounts a
        WHERE p.learning_account_id = a.id AND (p.display_name IS NULL OR p.email IS NULL)
        """
    )


def downgrade() -> None:
    op.drop_column("learning_course_participants", "email")
    op.drop_column("learning_course_participants", "display_name")
    op.execute(f"REVOKE SELECT (id) ON TABLE email_outbox FROM {ROLE}")
