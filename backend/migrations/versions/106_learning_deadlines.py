"""Дедлайн курса + напоминания (этап 2, ТЗ §15).

``learning_courses.deadline_at`` — опциональный срок прохождения;
``learning_course_participants.deadline_notified_at`` — отметка «напоминание
о дедлайне отправлено» (одно письмо на участника курса, дедлайны в письме —
из снапшота зачисления, латентности на эндпоинтах прохождения нет; cron ARQ
раз в сутки, письма через общий outbox).

Колонки существующих learning_*-таблиц: табличные гранты роли learning_app
из миграции 102 покрывают новые колонки целиком — отдельный GRANT не нужен.

Revision ID: 106
Revises: 105
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "106"
down_revision: str | None = "105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_courses",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learning_course_participants",
        sa.Column("deadline_notified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_course_participants", "deadline_notified_at")
    op.drop_column("learning_courses", "deadline_at")
