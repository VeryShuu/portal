"""Составные индексы попыток по (тест, участник) — ТЗ learning.md §7.

История/лимит попыток фильтруют по test_item_id + конкретному участнику
(``count_submitted``, ``my_attempts``, старт попытки); существующие одиночные
индексы по участнику и (test_item_id, submitted_at) заставляют PostgreSQL
фильтровать весь набор попыток участника. Ревью инкремента 6, P3.

Новые learning-миграции обязаны сами GRANT'ить роль (см. шапку 102) —
для индексов грант не нужен (объект таблицы, не данных).

Revision ID: 104
Revises: 103
Create Date: 2026-08-29
"""

from __future__ import annotations

from alembic import op

revision: str = "104"
down_revision: str | None = "103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_attempts_test_user "
        "ON learning_test_attempts (test_item_id, user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_attempts_test_account "
        "ON learning_test_attempts (test_item_id, learning_account_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_learning_attempts_test_account")
    op.execute("DROP INDEX IF EXISTS idx_learning_attempts_test_user")
