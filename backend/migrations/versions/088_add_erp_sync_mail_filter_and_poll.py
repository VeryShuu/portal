"""add erp_sync_settings: poll_enabled + mail filters

Revision ID: 088
Revises: 087
Create Date: 2026-07-31

ERP-синхронизация: расширение настроек приёма почты (docs/wip/erp-sync.md,
PR2). Миграция 087 создала ``erp_sync_settings`` с IMAP-блоком и базовым
расписанием; здесь добавляем:

* ``poll_enabled`` — отдельный переключатель авто-поллинга по cron. Двойной
  гейтинг: ``modules.erp_sync.enabled`` (вся фича) AND ``poll_enabled`` (только
  авто-забор). Без второго нельзя выключить поллинг, оставив ручной upload.
  Default ``FALSE`` — пока админ явно не включит.
* ``mail_subject_filter`` / ``mail_sender_filter`` / ``mail_attachment_filter``
  — три поля post-fetch фильтрации (общий ящик: на него сыплется разная почта,
  без фильтра импорт сломается на чужом письме). Все nullable/опциональны.

Фильтрация post-fetch (на стороне портала), а не через IMAP ``SEARCH SUBJECT``:
последний ненадёжен с MIME/B-encoded кириллицей (=?UTF-8?B?...?=). Письма мимо
фильтра **не** помечаются ``\\Seen`` (не трогаем чужую почту на общем ящике).

Zero-downtime: только additive ``ALTER TABLE``, без блокировок, без NOT NULL
без DEFAULT на существующем singleton-рядке (``id=1`` уже есть).
"""

from alembic import op

revision: str = "088"
down_revision: str | None = "087"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE erp_sync_settings
          ADD COLUMN poll_enabled           BOOLEAN     NOT NULL DEFAULT FALSE,
          ADD COLUMN mail_subject_filter    VARCHAR(255),
          ADD COLUMN mail_sender_filter     VARCHAR(255),
          ADD COLUMN mail_attachment_filter VARCHAR(255)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE erp_sync_settings
          DROP COLUMN mail_attachment_filter,
          DROP COLUMN mail_sender_filter,
          DROP COLUMN mail_subject_filter,
          DROP COLUMN poll_enabled
        """
    )
