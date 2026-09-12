"""Settings CRUD для ERP-sync (фильтры писём + переключатели).

IMAP-приёмка вынесена в общие настройки портала (ADR-048, вкладка Email).
Здесь остались только per-module настройки: ``enabled`` / ``poll_*`` /
``notify_emails`` и фильтры писём (``mail_subject_filter`` / ``mail_sender_filter``
/ ``mail_attachment_filter``).

Singleton-строка (``id=1``) уже создана миграцией 087 с defaults — поэтому
``GET`` всегда возвращает конфигурацию (``enabled=false`` по умолчанию).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import AdminDep, DbDep, RedisDep, require_erp_sync_module
from app.core.logging import get_logger
from app.models.erp_sync import ErpSyncSettings
from app.schemas.erp_sync import ErpSyncSettingsIn, ErpSyncSettingsOut
from app.services.audit import push_audit_event

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
        poll_interval_seconds=row.poll_interval_seconds,
        expected_interval_days=row.expected_interval_days,
        notify_emails=row.notify_emails,
        poll_enabled=row.poll_enabled,
        mail_subject_filter=row.mail_subject_filter,
        mail_sender_filter=row.mail_sender_filter,
        mail_attachment_filter=row.mail_attachment_filter,
        delete_after_fetch=row.delete_after_fetch,
        absences_poll_enabled=row.absences_poll_enabled,
        mail_absences_subject_filter=row.mail_absences_subject_filter,
        mail_absences_sender_filter=row.mail_absences_sender_filter,
        mail_absences_attachment_filter=row.mail_absences_attachment_filter,
        absences_expected_interval_days=row.absences_expected_interval_days,
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
    """Перенести per-module поля из payload в row.

    IMAP-приёмка теперь общая (ADR-048) — здесь только переключатели, расписание,
    уведомления и фильтры писём. ``poll_enabled=true`` без настроенного общего
    IMAP — валидно на уровне схемы, но cron-задача сама вернёт
    ``imap_not_configured`` (защита в run_erp_sync).
    """
    row.enabled = p.enabled
    row.poll_interval_seconds = p.poll_interval_seconds
    row.expected_interval_days = p.expected_interval_days
    row.notify_emails = p.notify_emails
    row.poll_enabled = p.poll_enabled
    row.mail_subject_filter = (p.mail_subject_filter or "").strip() or None
    row.mail_sender_filter = (p.mail_sender_filter or "").strip() or None
    row.mail_attachment_filter = (p.mail_attachment_filter or "").strip() or None
    row.delete_after_fetch = p.delete_after_fetch
    # Второй поток — отсутствия. Общие enabled/poll_interval/notify_emails выше;
    # per-потоковые переключатель и фильтры — здесь.
    row.absences_poll_enabled = p.absences_poll_enabled
    row.mail_absences_subject_filter = (p.mail_absences_subject_filter or "").strip() or None
    row.mail_absences_sender_filter = (p.mail_absences_sender_filter or "").strip() or None
    row.mail_absences_attachment_filter = (p.mail_absences_attachment_filter or "").strip() or None
    row.absences_expected_interval_days = p.absences_expected_interval_days
