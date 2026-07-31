"""move erp_sync IMAP to common email-settings (ADR-048)

Revision ID: 089
Revises: 088
Create Date: 2026-07-31

Вынос приёмки почты (IMAP) из модуля erp_sync в общие настройки портала
(``/data/branding/email-settings.json``, вкладка Email). Helpdesk не трогаем
(у него свой IMAP+SMTP, by-design). Фильтры писём (``mail_*_filter``) остаются
в ``erp_sync_settings`` как per-module настройки.

Этапы (zero-downtime):

1. **Бэкфилл**: читаем ``erp_sync_settings WHERE id=1``; если есть
   ``imap_host``/``imap_username`` — дописываем imap-блок в
   ``email-settings.json`` (imap_password_enc шифруется Fernet из SECRET_KEY).
   Защита: если в JSON уже есть ``imap_password_enc``/``imap_host`` — НЕ
   перезаписываем (админ уже настроил общий IMAP руками).
2. **DROP COLUMN**: удаляем ``imap_host/port/use_ssl/username/password_enc/folder``
   из ``erp_sync_settings`` (после бэкфилла данные в безопасности в JSON).

Fernet-шифр детерминирован от ``SECRET_KEY`` — бэкфилл корректен на любом
инстансе с тем же ключом (dev/прод). На диске IMAP-пароль лежит как
``imap_password_enc`` (Fernet), SMTP-пароль остаётся plaintext (намеренно).
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "089"
down_revision: str | None = "088"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

EMAIL_SETTINGS_FILE = Path("/data/branding/email-settings.json")


def _backfill_imap_to_email_settings() -> None:
    """Перенести IMAP-настройки из erp_sync_settings в email-settings.json.

    Делается в Python (нужен Fernet + чтение/запись JSON), данные erp_sync —
    через op.get_bind() (connection).
    """
    bind = op.get_bind()

    # 1. Читаем singleton erp_sync_settings (если таблица существует — она есть
    # с миграции 087). Берём только imap-колонки.
    row = bind.execute(
        # nosec B608 — статический SQL без интерполяции.
        text(
            "SELECT imap_host, imap_port, imap_use_ssl, imap_username, "
            "imap_password_enc, imap_folder "
            "FROM erp_sync_settings WHERE id = 1"
        )
    ).fetchone()

    if row is None or not row.imap_host or not row.imap_username:
        # Нечего переносить — IMAP у erp_sync не настроен.
        return

    # 2. Читаем существующий email-settings.json (если есть).
    existing: dict = {}
    if EMAIL_SETTINGS_FILE.exists():
        try:
            existing = json.loads(EMAIL_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            existing = {}

    # Защита: если общий IMAP уже настроен — не перезаписываем (админ сделал это
    # сам, либо миграция уже отрабатывала).
    if existing.get("imap_host") or existing.get("imap_password_enc"):
        return

    # 3. Шифруем пароль Fernet (переиспользуем secret_crypto — ключ из SECRET_KEY).
    # Импорт здесь (не на уровне модуля), чтобы не тащить Fernet-инициализацию
    # при загрузке миграции без настроенного SECRET_KEY.
    from app.core.secret_crypto import encrypt_secret

    imap_password_enc = ""
    if row.imap_password_enc:
        try:
            # Сначала расшифровываем старый шифр, затем шифруем заново (детерминированно
            # от того же ключа — фактически тот же токен, но безопасно при любом исходнике).
            from app.core.secret_crypto import decrypt_secret

            imap_password_enc = encrypt_secret(decrypt_secret(row.imap_password_enc))
        except Exception:
            # Старый шифр не читается — пропускаем пароль (админ перезадаст).
            imap_password_enc = ""

    existing["imap_host"] = row.imap_host
    existing["imap_port"] = row.imap_port or 993
    existing["imap_use_ssl"] = row.imap_use_ssl if row.imap_use_ssl is not None else True
    existing["imap_username"] = row.imap_username
    if imap_password_enc:
        existing["imap_password_enc"] = imap_password_enc
    existing["imap_folder"] = row.imap_folder or "INBOX"

    # 4. Запись (atomic_write через tmp + os.replace, chmod 0o600 — пароль в файле).
    EMAIL_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = EMAIL_SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, EMAIL_SETTINGS_FILE)
    with contextlib.suppress(OSError):
        os.chmod(EMAIL_SETTINGS_FILE, 0o600)


def upgrade() -> None:
    # 1. Бэкфилл ДО удаления колонок (данные ещё на месте).
    _backfill_imap_to_email_settings()

    # 2. DROP COLUMN imap_* из erp_sync_settings.
    op.execute(
        """
        ALTER TABLE erp_sync_settings
            DROP COLUMN IF EXISTS imap_host,
            DROP COLUMN IF EXISTS imap_port,
            DROP COLUMN IF EXISTS imap_use_ssl,
            DROP COLUMN IF EXISTS imap_username,
            DROP COLUMN IF EXISTS imap_password_enc,
            DROP COLUMN IF EXISTS imap_folder
        """
    )


def downgrade() -> None:
    # Восстанавливаем колонки (пустые — данные переехали в JSON, обратный
    # перенос не делаем; админ при необходимости перенастроит).
    op.execute(
        """
        ALTER TABLE erp_sync_settings
            ADD COLUMN imap_host       VARCHAR(255),
            ADD COLUMN imap_port       INTEGER NOT NULL DEFAULT 993,
            ADD COLUMN imap_use_ssl    BOOLEAN  NOT NULL DEFAULT TRUE,
            ADD COLUMN imap_username   VARCHAR(255),
            ADD COLUMN imap_password_enc TEXT,
            ADD COLUMN imap_folder     VARCHAR(100) NOT NULL DEFAULT 'INBOX'
        """
    )
