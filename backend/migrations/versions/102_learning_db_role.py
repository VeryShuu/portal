"""DB-роль модуля обучения (§10.8 ТЗ learning.md): learning_app + гранты

Revision ID: 102
Revises: 101
Create Date: 2026-08-27

Решение ТЗ («делать сразу нормально», Reydan 2026-08-26): второй SQLAlchemy
движок learning-роутов логинится под ролью ``learning_app``, у которой:
- SELECT/INSERT/UPDATE/DELETE только на ``learning_*``-таблицы;
- INSERT-only на общий ``email_outbox`` (outbox-письмо из learning-транзакции);
- ничего больше (аудит идёт через Redis, отдельный грант не нужен).

SELECT чужих таблиц под этой ролью невозможен на уровне СУБД — SQL-инъекция
или баг в learning-коде не выдаёт штатные данные. Пароль роли берётся из
env ``LEARNING_DB_PASSWORD`` напрямую (не через кэшируемые Settings: миграция
может выполняться в процессе, где Settings уже прогреты без этой переменной).
Без пароля роль создаётся без LOGIN-пароля (dev/тесты) — движок в этом
случае не переключается (см. app/core/database.py).

ВНИМАНИЕ для будущих learning-миграций: новые таблицы модуля обязаны
GRANT'иться роли в той же миграции — default privileges не настраивались
сознательно (иначе автогранты расползлись бы на немодульные таблицы).
"""

import os

from alembic import op

revision: str = "102"
down_revision: str | None = "101"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

ROLE = "learning_app"

# Все таблицы модуля из миграции 101 (в порядке зависимостей не важен).
LEARNING_TABLES = [
    "learning_accounts",
    "learning_password_resets",
    "learning_admins",
    "learning_courses",
    "learning_course_items",
    "learning_course_participants",
    "learning_tests",
    "learning_questions",
    "learning_question_options",
    "learning_test_attempts",
    "learning_item_progress",
]


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    # Роль идемпотентно (повторный прогон/восстановление из бэкапа не падают).
    op.execute(
        f"DO $$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') "
        f"THEN CREATE ROLE {ROLE} LOGIN; END IF; END$$;"
    )
    password = os.environ.get("LEARNING_DB_PASSWORD", "")
    if password:
        op.execute(f"ALTER ROLE {ROLE} LOGIN PASSWORD {_sql_literal(password)}")

    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {', '.join(LEARNING_TABLES)} TO {ROLE}"
    )
    op.execute(f"GRANT INSERT ON TABLE email_outbox TO {ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE INSERT ON TABLE email_outbox FROM {ROLE}")
    op.execute(
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {', '.join(LEARNING_TABLES)} FROM {ROLE}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {ROLE}")
