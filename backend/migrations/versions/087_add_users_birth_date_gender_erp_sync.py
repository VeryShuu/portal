"""add users.birth_date/gender + erp_sync_runs + erp_sync_settings

Revision ID: 087
Revises: 086
Create Date: 2026-07-31

ERP-синхронизация дней рождения и пола сотрудников (docs/wip/erp-sync.md).

Источник истины — ERP (1С): отчёт «Справочник: Сотрудники» приходит письмом
2 раза в неделю, портал забирает вложение по IMAP, парсит, сопоставляет ФИО и
записывает ``birth_date`` + ``gender`` в ``users``. Каждый импорт перетирает
значения (решение заказчика); компенсация — diff в отчёте админу после каждого
импорта.

Три части миграции:

1. ``users.birth_date`` (DATE) + ``users.gender`` (VARCHAR(10), CHECK male/female)
   — nullable, чтобы существующие пользователи не ломались. Видны всем
   авторизованным в карточке /staff (как телефоны).

2. ``erp_sync_runs`` — лог каждого импорта (idempotency по ``message_id`` для
   дедупа писем + JSONB-отчёт с разделами changed/unmatched/ambiguous/conflicts/
   errors для email-уведомления админу).

3. ``erp_sync_settings`` — singleton (``id = 1``) c IMAP-настройками ящика, на
   который ERP шлёт отчёты. Пароль — Fernet-шифр (как
   ``helpdesk_mailbox_settings.imap_password_enc``), plaintext write-only.
   ``poll_interval_seconds`` CHECK 60–3600 (крон опрашивает ящик),
   ``expected_interval_days`` — для watchdog-алерта «письма нет >N дней».

Zero-downtime: только additive ``ALTER TABLE``/``CREATE TABLE``, без блокировок,
без NOT NULL без DEFAULT на существующих строках.
"""

from alembic import op

revision: str = "087"
down_revision: str | None = "086"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Колонки сотрудника (nullable — назад совместимо).
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN birth_date DATE,
          ADD COLUMN gender     VARCHAR(10),
          ADD CONSTRAINT ck_users_gender CHECK (gender IS NULL OR gender IN ('male', 'female'))
        """
    )

    # 2. Лог импортов.
    op.execute(
        """
        CREATE TABLE erp_sync_runs (
            id              BIGSERIAL    PRIMARY KEY,
            message_id      TEXT         UNIQUE,
            attachment_hash TEXT,
            attachment_name TEXT,
            triggered_by    VARCHAR(20)  NOT NULL,
            started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            finished_at     TIMESTAMPTZ,
            status          VARCHAR(20)  NOT NULL,
            rows_total      INTEGER,
            rows_matched    INTEGER,
            rows_updated    INTEGER,
            rows_unmatched  INTEGER,
            rows_ambiguous  INTEGER,
            conflicts       INTEGER,
            errors          INTEGER,
            report          JSONB        NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_erp_sync_runs_triggered_by
                CHECK (triggered_by IN ('cron', 'manual')),
            CONSTRAINT ck_erp_sync_runs_status
                CHECK (status IN ('success', 'partial', 'failed', 'skipped'))
        )
        """
    )
    op.execute("CREATE INDEX ix_erp_sync_runs_started_at ON erp_sync_runs(started_at DESC)")

    # 3. Singleton настроек ящика (clone helpdesk_mailbox_settings).
    op.execute(
        """
        CREATE TABLE erp_sync_settings (
            id                      SMALLINT     PRIMARY KEY DEFAULT 1,
            enabled                 BOOLEAN      NOT NULL DEFAULT FALSE,
            imap_host               VARCHAR(255),
            imap_port               INTEGER      NOT NULL DEFAULT 993,
            imap_use_ssl            BOOLEAN      NOT NULL DEFAULT TRUE,
            imap_username           VARCHAR(255),
            imap_password_enc       TEXT,
            imap_folder             VARCHAR(100) NOT NULL DEFAULT 'INBOX',
            poll_interval_seconds   INTEGER      NOT NULL DEFAULT 900,
            expected_interval_days  INTEGER      NOT NULL DEFAULT 4,
            notify_emails           TEXT[],
            updated_by_user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_erp_sync_settings_singleton CHECK (id = 1),
            CONSTRAINT ck_erp_sync_settings_poll_interval
                CHECK (poll_interval_seconds BETWEEN 60 AND 3600)
        )
        """
    )
    op.execute("INSERT INTO erp_sync_settings (id) VALUES (1)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS erp_sync_settings")
    op.execute("DROP TABLE IF EXISTS erp_sync_runs")
    op.execute(
        """
        ALTER TABLE users
          DROP CONSTRAINT IF EXISTS ck_users_gender,
          DROP COLUMN IF EXISTS gender,
          DROP COLUMN IF EXISTS birth_date
        """
    )
