"""Описание/комментарий материала курса (rich-text, Markdown).

``learning_course_items.description`` — опциональное rich-описание элемента
(прод-запрос 2026-09-03: к материалу нужен комментарий с полноценным
редактором, как у описания курса). Sanitize на записи — тот же
``sanitize_markdown`` (nh3), что и у описания курса. Колонка nullable:
существующие элементы считаются без описания.

Колонки существующих learning_*-таблиц: табличные гранты роли learning_app
из миграции 102 покрывают новые колонки целиком — отдельный GRANT не нужен.

Revision ID: 108
Revises: 107
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "108"
down_revision: str | None = "107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_course_items",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_course_items", "description")
