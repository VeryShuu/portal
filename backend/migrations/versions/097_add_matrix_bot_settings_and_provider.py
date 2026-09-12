"""add matrix_bot_settings + messenger_outbox 'matrix' provider + keyset index

Revision ID: 097
Revises: 096
Create Date: 2026-08-16

Интеграция уведомлений портала с корпоративным чатом Matrix (Synapse + MAS):

1. ``matrix_bot_settings`` — singleton (``id=1``) с конфигурацией Matrix-бота:
   ``homeserver_url`` (API endpoint, может быть внутренним адресом),
   ``server_name`` (server-часть MXID, ``@localpart:server_name`` — MXID
   выводится из email пользователя конвенцией), ``access_token_enc``
   (Fernet через ``app.core.secret_crypto``, токен выдаётся
   ``mas-cli manage issue-compatibility-token``), ``bot_user_id`` (нужен для
   account_data ``m.direct`` — кэш DM-комнат бота). По образцу
   ``helpdesk_max_bot_settings`` (миграция 081): колонки nullable/DEFAULT,
   строка засевается сразу, ``enabled=False``.

2. CHECK ``ck_messenger_outbox_provider`` расширяется до ``('max','matrix')``
   — персональные уведомления идут в тот же transactional outbox.

3. Keyset-индекс ``ix_messenger_outbox_created_id (created_at DESC, id DESC)``
   для админской вкладки «Очередь мессенджеров» (зеркало миграции 091 для
   ``email_outbox``).

DDL вручную через ``op.execute`` (как 081-096): идемпотентно, zero-downtime
(новая таблица/индекс; пересоздание CHECK — краткая блокировкой на записи в
``messenger_outbox``, таблица маленькая).
"""

from alembic import op

revision: str = "097"
down_revision: str | None = "096"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── matrix_bot_settings (singleton, seeded) ────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS matrix_bot_settings (
            id                  SMALLINT    PRIMARY KEY DEFAULT 1,
            enabled             BOOLEAN     NOT NULL DEFAULT FALSE,
            homeserver_url      VARCHAR(255),
            server_name         VARCHAR(255) NOT NULL DEFAULT 'matrix.mage.ru',
            access_token_enc    TEXT,
            bot_user_id         VARCHAR(255),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT ck_matrix_bot_singleton CHECK (id = 1)
        )
        """
    )
    op.execute(
        """
        INSERT INTO matrix_bot_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
        """
    )

    # ── messenger_outbox: provider 'matrix' ────────────────────────────────
    op.execute(
        "ALTER TABLE messenger_outbox DROP CONSTRAINT IF EXISTS ck_messenger_outbox_provider"
    )
    op.execute(
        """
        ALTER TABLE messenger_outbox
        ADD CONSTRAINT ck_messenger_outbox_provider
        CHECK (provider IN ('max','matrix'))
        """
    )

    # ── keyset-пагинация для админ-списка (зеркало 091) ───────────────────
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messenger_outbox_created_id
            ON messenger_outbox (created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messenger_outbox_created_id")
    op.execute(
        "ALTER TABLE messenger_outbox DROP CONSTRAINT IF EXISTS ck_messenger_outbox_provider"
    )
    op.execute(
        """
        ALTER TABLE messenger_outbox
        ADD CONSTRAINT ck_messenger_outbox_provider
        CHECK (provider IN ('max'))
        """
    )
    op.execute("DROP TABLE IF EXISTS matrix_bot_settings CASCADE")
