"""Категории курсов обучения (справочник модуля).

``learning_course_categories`` — плоский упорядоченный справочник
(«Инструктажи», «ГО и ЧС», «Электробезопасность», …); управляет методист.
``learning_courses.category_id`` — необязательная привязка курса к категории;
на странице «Обучение» курсы группируются по категориям (прод-запрос
2026-09-03). FK ON DELETE SET NULL (AGENTS: ссылка на справочник не держит
курс); soft-delete категории дополнительно отвязывает курсы в сервисе.

Табличные гранты роли learning_app из миграции 102 на новую таблицу не
действуют (гранты таблицные на момент миграции) — выдаём ролью явные гранты.

Revision ID: 109
Revises: 108
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op

revision: str = "109"
down_revision: str | None = "108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_course_categories (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title       VARCHAR(255) NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_categories_order "
        "ON learning_course_categories (sort_order)"
    )
    op.execute(
        "ALTER TABLE learning_courses "
        "ADD COLUMN IF NOT EXISTS category_id UUID "
        "REFERENCES learning_course_categories(id) ON DELETE SET NULL"
    )
    # роль learning_app: справочник читается learning-роутами (§10.8)
    op.execute("GRANT SELECT ON learning_course_categories TO learning_app")
    op.execute("GRANT UPDATE (category_id) ON learning_courses TO learning_app")


def downgrade() -> None:
    op.execute("ALTER TABLE learning_courses DROP COLUMN IF EXISTS category_id")
    op.execute("DROP TABLE IF EXISTS learning_course_categories")
