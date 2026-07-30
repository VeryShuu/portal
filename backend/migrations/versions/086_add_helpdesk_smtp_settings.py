"""add SMTP settings to helpdesk_mailbox_settings

Revision ID: 086
Revises: 085
Create Date: 2026-07-30

Helpdesk раньше принимал заявки с настроенного support-ящика (IMAP), но
отправлял ответы через общий порталный SMTP (``/data/branding/email-settings.json``,
``From: portal@company.local``). Это рассогласовывало адрес приёма и адрес
отправки: заявитель получал письмо «от портала», а отвечал — в support-ящик.

Добавляем собственный SMTP-блок рядом с IMAP (``helpdesk_mailbox_settings``):
``smtp_host``/``smtp_port``/``smtp_username``/``smtp_password_enc``/
``smtp_use_tls``/``smtp_use_starttls``. Воркер ``process_email_outbox``
маршрутизирует всю helpdesk-почту (``kind=helpdesk`` + ``kind=generic`` c
маркером ``payload.smtp_source="helpdesk"``) на этот SMTP, логинясь под
учёткой support-ящика — ``From:``, envelope MAIL FROM и SMTP-auth становятся
консистентны с адресом приёма.

Все колонки **nullable**: существующий singleton-рядок (``id=1``) не ломается.
При пустом ``smtp_host`` воркер fallback'ит на общий SMTP портала
(backward-compatible). Пароль — шифр Fernet (как ``imap_password_enc``),
plaintext write-only. Defaults по образцу порталных ``EmailSettings``.

Zero-downtime: только additive ``ALTER TABLE ... ADD COLUMN``, без блокировок.
"""

from alembic import op

revision: str = "086"
down_revision: str | None = "085"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE helpdesk_mailbox_settings
          ADD COLUMN smtp_host          VARCHAR(255),
          ADD COLUMN smtp_port          INTEGER     NOT NULL DEFAULT 25,
          ADD COLUMN smtp_username      VARCHAR(255),
          ADD COLUMN smtp_password_enc  TEXT,
          ADD COLUMN smtp_use_tls       BOOLEAN     NOT NULL DEFAULT FALSE,
          ADD COLUMN smtp_use_starttls  BOOLEAN     NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE helpdesk_mailbox_settings
          DROP COLUMN smtp_use_starttls,
          DROP COLUMN smtp_use_tls,
          DROP COLUMN smtp_password_enc,
          DROP COLUMN smtp_username,
          DROP COLUMN smtp_port,
          DROP COLUMN smtp_host
        """
    )
