"""add directum integration (settings singleton + runs log)

Revision ID: 098
Revises: 097
Create Date: 2026-08-17

Интеграция с СЭД Directum (docs/directum.md). Первая задача — «Просроченные
задачи»: cron запрашивает OData ``IAssignments`` (``Deadline lt NOW and Status
eq 'InProcess'``) с basic auth сервисной AD-учётки, сопоставляет ФИО
исполнителей с ``users.full_name`` и шлёт дайджесты в личные чаты Matrix
(opt-in ``chat_notifications_enabled``) + email-сводку админам.

Архитектурно — клон erp_sync (миграции 087/092) с HTTP-источником вместо IMAP:

* ``directum_settings`` — singleton (``id=1``): общие настройки + per-задачная
  колонка-группа ``overdue_*`` (как ``absences_*`` в erp_sync). Пароль —
  Fernet-шифр ``auth_password_enc`` (write-only в API).
* ``directum_runs`` — лог прогонов со счётчиками и JSONB-отчётом (клон
  ``erp_sync_runs``; ``message_id`` не нужен — источника-письма нет, дедупа
  по решению пользователя тоже: уведомляем каждый прогон).

Все изменения additive (zero-downtime): CREATE TABLE + seeded singleton.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "098"
down_revision: str | None = "097"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Singleton настроек (id=1, сеется сразу — GET /directum/settings всегда отвечает).
    # nosec B608 — статический DDL без интерполяции.
    op.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS directum_settings (
                id                   SMALLINT PRIMARY KEY,
                enabled              BOOL NOT NULL DEFAULT FALSE,
                base_url             VARCHAR(255) NOT NULL
                    DEFAULT 'https://sed.mage.ru/Integration/odata',
                auth_username        VARCHAR(255),
                auth_password_enc    TEXT,
                poll_interval_seconds INT NOT NULL DEFAULT 86400,
                expected_interval_days INT NOT NULL DEFAULT 2,
                notify_emails        TEXT[],
                overdue_enabled      BOOL NOT NULL DEFAULT FALSE,
                updated_by_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_directum_settings_singleton CHECK (id = 1),
                CONSTRAINT ck_directum_settings_poll_interval
                    CHECK (poll_interval_seconds BETWEEN 300 AND 86400)
            )
            """
        )
    )
    op.execute(text("INSERT INTO directum_settings (id) VALUES (1) ON CONFLICT DO NOTHING"))

    # 2. Лог прогонов (клон erp_sync_runs без message_id/attachment_* — источника-письма нет).
    op.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS directum_runs (
                id                  BIGSERIAL PRIMARY KEY,
                triggered_by        VARCHAR(20) NOT NULL,
                started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                finished_at         TIMESTAMPTZ,
                status              VARCHAR(20) NOT NULL,
                tasks_total         INT,
                performers_total    INT,
                users_notified      INT,
                users_skipped_opt_in INT,
                users_unmatched     INT,
                users_ambiguous     INT,
                errors              INT,
                report              JSONB NOT NULL DEFAULT '{}'::jsonb,
                CONSTRAINT ck_directum_runs_triggered_by
                    CHECK (triggered_by IN ('cron', 'manual')),
                CONSTRAINT ck_directum_runs_status
                    CHECK (status IN ('success', 'partial', 'failed', 'skipped'))
            )
            """
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_directum_runs_started_at "
            "ON directum_runs (started_at DESC)"
        )
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_directum_runs_started_at"))
    op.execute(text("DROP TABLE IF EXISTS directum_runs"))
    op.execute(text("DROP TABLE IF EXISTS directum_settings"))
