"""Сертификаты о прохождении курса (этап 2, ТЗ §15).

Одна строка = выданный сертификат: участник (XOR-принципал, как в
participants/progress/attempts) + курс + серийный номер + путь к PDF в
``/data/learning/certificates/``. Выдача ленивая, при первом запросе
участником после полного прохождения; повторные запросы отдают сохранённый
файл (серийник и дата неизменны).

Новые learning-миграции обязаны сами GRANT'ить роль (см. шапку 102).

Revision ID: 105
Revises: 104
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "105"
down_revision: str | None = "104"
branch_labels = None
depends_on = None

ROLE = "learning_app"


def upgrade() -> None:
    op.create_table(
        "learning_certificates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "course_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "learning_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("serial", sa.String(16), nullable=False, unique=True),
        sa.Column("pdf_path", sa.String(512), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "((user_id IS NOT NULL)::int + (learning_account_id IS NOT NULL)::int) = 1",
            name="ck_learning_certificates_participant_xor",
        ),
    )
    # Уникальность «один сертификат на участника курса» — частичными индексами
    # (обычный UNIQUE с nullable-колонками пропускает дубли).
    op.create_index(
        "uq_learning_certificates_user",
        "learning_certificates",
        ["course_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_learning_certificates_account",
        "learning_certificates",
        ["course_id", "learning_account_id"],
        unique=True,
        postgresql_where=sa.text("learning_account_id IS NOT NULL"),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE learning_certificates TO {ROLE}")


def downgrade() -> None:
    op.drop_table("learning_certificates")
