"""Курсы «для всех сотрудников» (for_all_staff).

``learning_courses.for_all_staff`` — флаг обязательного курса: любой
активный сотрудник портала является участником автоматически, включая
созданных ПОСЛЕ включения флага (аналог группы «Все пользователи» в ACL
файлов/фото, прод-запрос 2026-09-03). Внешние учётки флаг не затрагивает —
они зачисляются явно.

Доступ виртуальный (проверяется на лету), а строки участников
материализуются для панелей/экспорта/cron: при включении флага (роутер
проводит всех активных сотрудников без явной строки) и после каждого
прогона Keycloak-синка (worker/tasks/news.py — set-based INSERT для новых).
Письма при массовом покрытии не рассылаются — только точечные зачисления.

Колонки существующей таблицы: гранты роли learning_app покрывают их целиком.

Revision ID: 111
Revises: 110
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op

revision: str = "111"
down_revision: str | None = "110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE learning_courses "
        "ADD COLUMN IF NOT EXISTS for_all_staff BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE learning_courses DROP COLUMN IF EXISTS for_all_staff")
