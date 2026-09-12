"""directum: расписание «часы запуска» вместо общего интервала прогона

Revision ID: 099
Revises: 098
Create Date: 2026-08-17

Решение зафиксировано с пользователем: общий ``poll_interval_seconds`` убран;
у каждой задачи своё расписание — список часов запуска (только часы, минуты
не настраиваются; время московское +03:00, как у самого Directum). Пример:
10, 12, 14 — прогоны в 10:17, 12:17, 14:17 MSK (cron тикает ежечасно в :17).

* ``directum_settings.poll_interval_seconds`` — DROP (модуль ещё не на проду,
  данных для миграции нет).
* ``directum_settings.overdue_run_hours INTEGER[] NOT NULL DEFAULT '{}'`` —
  часы задачи «Просроченные задачи» в московском времени; пустой массив =
  авто-прогонов нет (ручной запуск работает). CHECK ``<@`` гарантирует, что
  все элементы — валидные часы 0..23.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "099"
down_revision: str | None = "098"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE directum_settings "
            "ADD COLUMN IF NOT EXISTS overdue_run_hours INTEGER[] NOT NULL DEFAULT '{}'"
        )
    )
    op.execute(
        text(
            "ALTER TABLE directum_settings DROP CONSTRAINT IF EXISTS "
            "ck_directum_settings_poll_interval"
        )
    )
    op.execute(text("ALTER TABLE directum_settings DROP COLUMN IF EXISTS poll_interval_seconds"))
    # <@ («подмножество») — компактный CHECK «все элементы — часы 0..23».
    # nosec B608 — статический DDL без интерполяции.
    op.execute(
        text(
            "ALTER TABLE directum_settings "
            "ADD CONSTRAINT ck_directum_settings_run_hours CHECK ("
            "overdue_run_hours <@ ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,"
            "12,13,14,15,16,17,18,19,20,21,22,23])"
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE directum_settings DROP CONSTRAINT IF EXISTS ck_directum_settings_run_hours"
        )
    )
    op.execute(text("ALTER TABLE directum_settings DROP COLUMN IF EXISTS overdue_run_hours"))
    op.execute(
        text(
            "ALTER TABLE directum_settings "
            "ADD COLUMN IF NOT EXISTS poll_interval_seconds INT NOT NULL DEFAULT 86400"
        )
    )
    op.execute(
        text(
            "ALTER TABLE directum_settings "
            "ADD CONSTRAINT ck_directum_settings_poll_interval "
            "CHECK (poll_interval_seconds BETWEEN 300 AND 86400)"
        )
    )
