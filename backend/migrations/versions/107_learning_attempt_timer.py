"""Таймер попытки теста (этап 2, ТЗ §15).

``learning_tests.time_limit_minutes`` — опциональный лимит времени на
попытку (NULL = без ограничения). Серверный контроль: submit после
``started_at + лимит`` отклоняется (409), попытка клеймится abandoned.
Правка лимита после первой попытки уже закрыта замком §15 — лимит не может
«доигрываться» задним числом.

Колонка существующей learning_*-таблицы: гранты роли из миграции 102
действуют (табличные).

Revision ID: 107
Revises: 106
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "107"
down_revision: str | None = "106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_tests",
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_learning_tests_time_limit",
        "learning_tests",
        "time_limit_minutes IS NULL OR (time_limit_minutes >= 1 AND time_limit_minutes <= 600)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_learning_tests_time_limit", "learning_tests", type_="check")
    op.drop_column("learning_tests", "time_limit_minutes")
