"""Гранты роли learning_app на таблицу категорий курсов (фикс 109).

Миграция 109 выдала роли только SELECT, хотя справочник управляется
методистом через admin-роуты на learning-движке: INSERT (создание),
UPDATE (переименование/reorder/soft-delete) падали
InsufficientPrivilegeError → 500 на POST /learning/admin/categories
(прод-кейс 2026-09-03, контур с заданным LEARNING_DB_PASSWORD).
DELETE роли не нужен (удаление только soft), но выдаётся симметрично
грантам 102/105 — RW на таблицы модуля.

Revision ID: 112
Revises: 111
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op

revision: str = "112"
down_revision: str | None = "111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON learning_course_categories TO learning_app")


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON learning_course_categories FROM learning_app"
    )
