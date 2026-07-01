"""Admin mailbox settings for helpdesk (Этап 5, ТЗ §3.6, §9.2).

Singleton-строка (``id=1``) с IMAP-конфигом. Пароль шифруется через
``secret_crypto`` (write-only: в ответах только ``imap_password_set``).
``GET`` до первого ``PUT`` возвращает ``configured=false`` (строка ещё не
создана — ``imap_password_enc NOT NULL`` не даёт засеять её без пароля).
``POST /test`` проверяет IMAP-соединение.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.models.helpdesk import HelpdeskDigestSettings, HelpdeskMailboxSettings
from app.schemas.helpdesk import (
    HelpdeskDigestSettingsIn,
    HelpdeskDigestSettingsOut,
    HelpdeskMailboxSettingsIn,
    HelpdeskMailboxSettingsOut,
)
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(prefix="/helpdesk/settings", tags=["helpdesk"])


async def _load_singleton(db: DbDep) -> HelpdeskMailboxSettings | None:
    res = await db.execute(
        select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1)
    )
    row = res.scalars().one_or_none()
    return row


def _to_out(row: HelpdeskMailboxSettings | None) -> HelpdeskMailboxSettingsOut:
    if row is None:
        return HelpdeskMailboxSettingsOut(configured=False)
    return HelpdeskMailboxSettingsOut(
        configured=True,
        imap_host=row.imap_host,
        imap_port=row.imap_port,
        imap_username=row.imap_username,
        imap_password_set=True,
        imap_use_ssl=row.imap_use_ssl,
        imap_folder=row.imap_folder,
        poll_interval_seconds=row.poll_interval_seconds,
        delete_after_fetch=row.delete_after_fetch,
        support_address=row.support_address,
        support_reply_to=row.support_reply_to,
        updated_at=row.updated_at,
    )


@router.get("/mailbox", response_model=HelpdeskMailboxSettingsOut)
async def get_mailbox_settings(_admin: AdminDep, db: DbDep) -> HelpdeskMailboxSettingsOut:
    return _to_out(await _load_singleton(db))


@router.put("/mailbox", response_model=HelpdeskMailboxSettingsOut)
async def put_mailbox_settings(
    payload: HelpdeskMailboxSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> HelpdeskMailboxSettingsOut:
    row = await _load_singleton(db)
    if row is None:
        # Создание singleton'а: пароль обязателен (без него NOT NULL-колонка).
        if not payload.imap_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="imap_password is required on first configuration",
            )
        row = HelpdeskMailboxSettings(id=1, updated_by_user_id=admin.id)
        _apply_fields(row, payload, is_create=True)
        db.add(row)
    else:
        # Обновление: пароль опционален (None = оставить прежний шифр).
        row.updated_by_user_id = admin.id
        _apply_fields(row, payload, is_create=False)

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="helpdesk.mailbox_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_mailbox_settings",
        resource_id="1",
        metadata={"support_address": payload.support_address},
    )
    return _to_out(row)


def _apply_fields(
    row: HelpdeskMailboxSettings, p: HelpdeskMailboxSettingsIn, *, is_create: bool
) -> None:
    row.imap_host = p.imap_host
    row.imap_port = p.imap_port
    row.imap_username = p.imap_username
    if p.imap_password:  # write-only: пусто/None = оставить прежний шифр
        row.imap_password_enc = encrypt_secret(p.imap_password)
    elif is_create:
        # На случай если валидация пропустила пустой пароль при создании.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="imap_password is required on first configuration",
        )
    row.imap_use_ssl = p.imap_use_ssl
    row.imap_folder = p.imap_folder
    row.poll_interval_seconds = p.poll_interval_seconds
    row.delete_after_fetch = p.delete_after_fetch
    row.support_address = p.support_address
    row.support_reply_to = p.support_reply_to


@router.post("/mailbox/test")
async def test_mailbox_connection(_admin: AdminDep, db: DbDep) -> dict:
    """Проверка IMAP-соединения с текущими настройками. Возвращает OK/детали."""
    row = await _load_singleton(db)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not configured"
        )
    password = decrypt_secret(row.imap_password_enc)
    try:
        from app.services.helpdesk.ingress import probe_imap_connection

        ok, detail = await probe_imap_connection(
            host=row.imap_host,
            port=row.imap_port,
            username=row.imap_username,
            password=password,
            use_ssl=row.imap_use_ssl,
            folder=row.imap_folder,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": ok, "detail": detail}


# ---------------------------------------------------------------------------
# Daily digest settings (singleton, seeded by migration 076).
# ---------------------------------------------------------------------------


async def _load_digest_singleton(db: DbDep) -> HelpdeskDigestSettings:
    """Singleton helpdesk_digest_settings (id=1).

    В отличие от mailbox, строка засевается миграцией — всегда существует.
    Защитный fallback: если миграция ещё не применена/строка удалена, создаём
    новую с дефолтами (best-effort; нормальный путь — миграция).
    """
    res = await db.execute(
        select(HelpdeskDigestSettings).where(HelpdeskDigestSettings.id == 1)
    )
    row = res.scalars().one_or_none()
    if row is None:
        row = HelpdeskDigestSettings(id=1)
        db.add(row)
        await db.flush()
    return row


@router.get("/digest", response_model=HelpdeskDigestSettingsOut)
async def get_digest_settings(_admin: AdminDep, db: DbDep) -> HelpdeskDigestSettingsOut:
    row = await _load_digest_singleton(db)
    return HelpdeskDigestSettingsOut.model_validate(row)


@router.put("/digest", response_model=HelpdeskDigestSettingsOut)
async def put_digest_settings(
    payload: HelpdeskDigestSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> HelpdeskDigestSettingsOut:
    row = await _load_digest_singleton(db)
    row.enabled = payload.enabled
    row.digest_hour = payload.digest_hour
    row.digest_minute = payload.digest_minute
    row.digest_schedule = payload.digest_schedule
    row.updated_by_user_id = admin.id
    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="helpdesk.digest_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_digest_settings",
        resource_id="1",
        metadata={
            "enabled": payload.enabled,
            "digest_hour": payload.digest_hour,
            "digest_minute": payload.digest_minute,
            "digest_schedule": payload.digest_schedule,
        },
    )
    return HelpdeskDigestSettingsOut.model_validate(row)

