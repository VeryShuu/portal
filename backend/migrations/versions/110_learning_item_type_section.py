"""Разделы курса: строки-заголовки среди элементов (тип 'section').

Группировка материалов и тестов поименованными блоками («Нормативные
документы», «Инструкции», …; прод-запрос 2026-09-03). Раздел — обычная
строка ``learning_course_items`` с типом 'section': перенос материала между
разделами = перестановка строк, reorder-механика работает как есть.

Инварианты:
- разделы НЕ участвуют в прогрессе (учитываются только material/test);
- у раздела нет url/description/файла; «отметить ознакомленным» для него
  отвечает 422 (уже охраняется complete_material);
- добавлять/удалять разделы можно и в опубликованном курсе: заголовок не
  влияет на проходимость (publish-gate не задет).

Revision ID: 110
Revises: 109
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op

revision: str = "110"
down_revision: str | None = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE learning_course_items DROP CONSTRAINT IF EXISTS ck_learning_items_type")
    op.execute(
        "ALTER TABLE learning_course_items "
        "ADD CONSTRAINT ck_learning_items_type "
        "CHECK (type IN ('material', 'test', 'section'))"
    )


def downgrade() -> None:
    # разделы с публикацией типа не совместимы — удаляем их строки
    op.execute("DELETE FROM learning_course_items WHERE type = 'section'")
    op.execute("ALTER TABLE learning_course_items DROP CONSTRAINT IF EXISTS ck_learning_items_type")
    op.execute(
        "ALTER TABLE learning_course_items "
        "ADD CONSTRAINT ck_learning_items_type CHECK (type IN ('material', 'test'))"
    )
