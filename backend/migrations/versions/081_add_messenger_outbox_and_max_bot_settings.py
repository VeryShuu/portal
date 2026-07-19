"""add messenger_outbox + helpdesk_max_bot_settings (MAX messenger integration)

Revision ID: 081
Revises: 080
Create Date: 2026-07-19

Две таблицы для интеграции уведомлений helpdesk с мессенджером MAX (max.ru):

1. ``messenger_outbox`` — transactional outbox для исходящих сообщений в
   мессенджеры (зеркало ``email_outbox``). Поле ``provider`` зарезервировано
   для будущих провайдеров (Telegram/Slack); сейчас используется только
   ``'max'``. Доставка — cron-воркер ``process_messenger_outbox`` каждые 15с,
   claim через ``FOR UPDATE SKIP LOCKED``, retry/backoff/DLQ.

   Отличие от ``email_outbox``: вместо ``to_email``/``subject``/``body_html``/
   ``body_text`` — ``chat_id`` + ``text`` + ``payload`` (JSONB с attachments,
   форматом, метаданными). ``payload`` хранит всё, что нужно провайдеру:
   inline-keyboard, формат разметки (markdown/html), additional metadata.

2. ``helpdesk_max_bot_settings`` — singleton (``id=1``) с конфигурацией MAX-бота
   (токен + chat_id общего чата поддержки). По образцу
   ``helpdesk_digest_settings`` (миграция 076): все колонки nullable/DEFAULT,
   строка засевается сразу, ``enabled=False`` по умолчанию → фича выключена,
   пока админ не активирует её в Helpdesk-вкладке. ``bot_token_enc`` шифруется
   через ``app.core.secret_crypto`` (Fernet из ``SECRET_KEY``), как IMAP-пароль.

DDL написан вручную через ``op.execute`` (как 075-080): ``IF NOT EXISTS`` делает
миграцию идемпотентной, zero-downtime (новые таблицы, без блокировок существующих).
"""

from alembic import op

revision: str = "081"
down_revision: str | None = "080"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── messenger_outbox ────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messenger_outbox (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider               VARCHAR(32)  NOT NULL,
            chat_id                VARCHAR(64)  NOT NULL,
            text                   TEXT         NOT NULL,
            payload                JSONB        NOT NULL DEFAULT '{}'::jsonb,
            status                 VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
            attempts               INTEGER      NOT NULL DEFAULT 0,
            max_attempts           INTEGER      NOT NULL DEFAULT 6,
            next_attempt_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_error_type        VARCHAR(128),
            last_error_class       VARCHAR(16),
            last_error             TEXT,
            sent_at                TIMESTAMPTZ,
            related_resource_type  VARCHAR(64),
            related_resource_id    UUID,
            created_by_user_id     UUID,
            created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_messenger_outbox_status
                CHECK (status IN ('PENDING','SENDING','SENT','FAILED','DLQ','CANCELLED')),
            CONSTRAINT ck_messenger_outbox_provider
                CHECK (provider IN ('max'))
        )
        """
    )
    # Claim-очередь: воркер ищет PENDING с подошедшим next_attempt_at.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messenger_outbox_pending
            ON messenger_outbox (next_attempt_at)
            WHERE status = 'PENDING'
        """
    )
    # Watchdog: поиск «зависших» SENDING (воркер упал между claim и mark_sent).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messenger_outbox_stale
            ON messenger_outbox (updated_at)
            WHERE status = 'SENDING'
        """
    )

    # ── helpdesk_max_bot_settings (singleton, seeded) ───────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS helpdesk_max_bot_settings (
            id                  SMALLINT    PRIMARY KEY DEFAULT 1,
            enabled             BOOLEAN     NOT NULL DEFAULT FALSE,
            bot_token_enc       TEXT,
            chat_id             VARCHAR(64),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT ck_helpdesk_max_bot_singleton CHECK (id = 1)
        )
        """
    )
    # Seed singleton row (enabled=False по умолчанию → фича выключена, пока
    # админ не активирует). ON CONFLICT — для идемпотентности при повторном
    # применении миграции (например, при развертывании на новой БД).
    op.execute(
        """
        INSERT INTO helpdesk_max_bot_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS helpdesk_max_bot_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS messenger_outbox CASCADE")
