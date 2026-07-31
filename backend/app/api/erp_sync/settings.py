"""Settings CRUD + IMAP-test для ERP-sync (клон helpdesk/settings.py).

Singleton-строка (``id=1``) уже создана миграцией 087 с defaults — поэтому
``GET`` всегда возвращает конфигурацию (``enabled=false`` по умолчанию).
Пароль write-only: в ответе только ``imap_password_set: bool``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import AdminDep, DbDep, RedisDep, require_erp_sync_module
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.models.erp_sync import ErpSyncSettings
from app.schemas.erp_sync import ErpSyncSettingsIn, ErpSyncSettingsOut, ErpSyncTestResult
from app.services.audit import push_audit_event
from app.services.erp_sync.mailbox import probe_imap_connection

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_erp_sync_module)])


async def _load_singleton(db: DbDep) -> ErpSyncSettings:
    """Singleton всегда существует (миграция 087 INSERT id=1)."""
    res = await db.execute(select(ErpSyncSettings).where(ErpSyncSettings.id == 1))
    row = res.scalars().one_or_none()
    if row is None:
        # Теоретически невозможно (миграция сеет), но защитно создаём.
        row = ErpSyncSettings(id=1)
        db.add(row)
    return row


def _to_out(row: ErpSyncSettings) -> ErpSyncSettingsOut:
    return ErpSyncSettingsOut(
        enabled=row.enabled,
        imap_host=row.imap_host,
        imap_port=row.imap_port,
        imap_use_ssl=row.imap_use_ssl,
        imap_username=row.imap_username,
        imap_password_set=bool(row.imap_password_enc),
        imap_folder=row.imap_folder,
        poll_interval_seconds=row.poll_interval_seconds,
        expected_interval_days=row.expected_interval_days,
        notify_emails=row.notify_emails,
        poll_enabled=row.poll_enabled,
        mail_subject_filter=row.mail_subject_filter,
        mail_sender_filter=row.mail_sender_filter,
        mail_attachment_filter=row.mail_attachment_filter,
        updated_at=row.updated_at,
    )


@router.get("/settings", response_model=ErpSyncSettingsOut)
async def get_settings(_admin: AdminDep, db: DbDep) -> ErpSyncSettingsOut:
    return _to_out(await _load_singleton(db))


@router.put("/settings", response_model=ErpSyncSettingsOut)
async def put_settings(
    payload: ErpSyncSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> ErpSyncSettingsOut:
    row = await _load_singleton(db)
    row.updated_by_user_id = admin.id
    _apply_fields(row, payload)
    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="erp_sync.settings_updated",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="erp_sync_settings",
        resource_id="1",
        metadata={"enabled": payload.enabled, "poll_enabled": payload.poll_enabled},
    )
    logger.info(
        "erp_sync.settings_updated",
        enabled=payload.enabled,
        poll_enabled=payload.poll_enabled,
        by=str(admin.id),
    )
    return _to_out(row)


def _apply_fields(row: ErpSyncSettings, p: ErpSyncSettingsIn) -> None:
    """Перенести поля из payload в row. Пароль write-only.

    IMAP-блок целиком nullable (в отличие от helpdesk): модуль можно
    сконфигурить с пустым ящиком и включить позже. ``poll_enabled=true`` без
    настроенного IMAP — валидно на уровне схемы, но cron-задача сама вернёт
    ``imap_not_configured`` (защита в run_erp_sync).
    """
    row.enabled = p.enabled
    row.imap_host = (p.imap_host or "").strip() or None
    row.imap_port = p.imap_port
    row.imap_use_ssl = p.imap_use_ssl
    row.imap_username = (p.imap_username or "").strip() or None
    if p.imap_password:  # write-only: пусто/None = оставить прежний шифр
        row.imap_password_enc = encrypt_secret(p.imap_password)
    row.imap_folder = p.imap_folder
    row.poll_interval_seconds = p.poll_interval_seconds
    row.expected_interval_days = p.expected_interval_days
    row.notify_emails = p.notify_emails
    row.poll_enabled = p.poll_enabled
    row.mail_subject_filter = (p.mail_subject_filter or "").strip() or None
    row.mail_sender_filter = (p.mail_sender_filter or "").strip() or None
    row.mail_attachment_filter = (p.mail_attachment_filter or "").strip() or None


@router.post("/test", response_model=ErpSyncTestResult)
async def test_connection(_admin: AdminDep, db: DbDep) -> ErpSyncTestResult:
    """Проверка IMAP-подключения (login + select folder).

    Маскируем исключения: aioimaplib в некоторых из них echo'ит LOGIN-команду
    с паролем (грабля H-9 из helpdesk).
    """
    row = await _load_singleton(db)
    if not row.imap_host or not row.imap_username or not row.imap_password_enc:
        return ErpSyncTestResult(ok=False, error="IMAP не настроен (host/username/password).")
    password = decrypt_secret(row.imap_password_enc)
    try:
        ok, detail = await probe_imap_connection(
            host=row.imap_host,
            port=row.imap_port,
            username=row.imap_username,
            password=password,
            use_ssl=row.imap_use_ssl,
            folder=row.imap_folder,
        )
    except Exception:
        # H-9: не возвращаем str(exc) — может содержать пароль.
        logger.exception("erp_sync.test_connection_failed")
        return ErpSyncTestResult(ok=False, error="Ошибка подключения (см. логи сервера).")
    if ok:
        return ErpSyncTestResult(ok=True)
    # detail из probe может содержать тип исключения — scrubb'им.
    safe = detail if len(detail) < 200 else detail[:200] + "…"
    return ErpSyncTestResult(ok=False, error=safe)
