"""Settings CRUD для Directum (подключение + расписание + получатели).

Пароль write-only (Fernet, ``auth_password_enc``): в ответе только
``password_set: bool``; пустой пароль в PUT = «оставить прежний» (паттерн
matrix-бота). ``enabled=true`` требует полного набора кредов — иначе 400.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AdminDep, DbDep, RedisDep, require_directum_module
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.models.directum import DirectumSettings
from app.schemas.directum import (
    DirectumSettingsIn,
    DirectumSettingsOut,
    DirectumTestResult,
)
from app.services.audit import push_audit_event
from app.services.directum.odata import DirectumApiError, ping
from app.services.directum.sync import directum_configured, load_directum_settings

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_directum_module)])


async def _load_singleton(db: DbDep) -> DirectumSettings:
    """Singleton всегда существует (миграция 098 INSERT id=1); защитно создаём."""
    row = await load_directum_settings(db)
    if row is None:
        row = DirectumSettings(id=1)
        db.add(row)
        await db.flush()
    return row


def _to_out(row: DirectumSettings) -> DirectumSettingsOut:
    password_set = bool(row.auth_password_enc)
    return DirectumSettingsOut(
        enabled=row.enabled,
        base_url=row.base_url,
        auth_username=row.auth_username,
        password_set=password_set,
        configured=bool(row.base_url and row.auth_username and password_set),
        overdue_run_hours=row.overdue_run_hours,
        expected_interval_days=row.expected_interval_days,
        notify_emails=row.notify_emails,
        overdue_enabled=row.overdue_enabled,
        updated_at=row.updated_at,
    )


@router.get("/settings", response_model=DirectumSettingsOut)
async def get_settings(_admin: AdminDep, db: DbDep) -> DirectumSettingsOut:
    return _to_out(await _load_singleton(db))


@router.put("/settings", response_model=DirectumSettingsOut)
async def put_settings(
    payload: DirectumSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> DirectumSettingsOut:
    row = await _load_singleton(db)
    row.updated_by_user_id = admin.id
    row.enabled = payload.enabled
    row.base_url = payload.base_url
    row.auth_username = payload.auth_username
    if payload.auth_password:  # write-only: пусто/None = оставить прежний шифр
        row.auth_password_enc = encrypt_secret(payload.auth_password)
    row.overdue_run_hours = payload.overdue_run_hours
    row.expected_interval_days = payload.expected_interval_days
    row.notify_emails = payload.notify_emails
    row.overdue_enabled = payload.overdue_enabled

    if row.enabled and not directum_configured(row):
        missing = [
            label
            for label, value in (
                ("base_url", row.base_url),
                ("auth_username", row.auth_username),
                ("auth_password", row.auth_password_enc),
            )
            if not value
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"required when enabled=true: {', '.join(missing)}",
        )
    # UX-урок «молчаливое ничегонеделанье»: включённая задача без часов
    # расписания никогда бы не запускалась — требуем хотя бы один час.
    if row.overdue_enabled and not row.overdue_run_hours:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="overdue_enabled=true requires at least one run hour",
        )

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="directum.settings_updated",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="directum_settings",
        resource_id="1",
        metadata={
            "enabled": payload.enabled,
            "overdue_enabled": payload.overdue_enabled,
            "password_changed": bool(payload.auth_password),
        },
    )
    logger.info(
        "directum.settings_updated",
        enabled=payload.enabled,
        overdue_enabled=payload.overdue_enabled,
        by=str(admin.id),
    )
    return _to_out(row)


@router.post("/test", response_model=DirectumTestResult)
async def check_connection(admin: AdminDep, db: DbDep) -> DirectumTestResult:
    """Синхронная проверка OData: доступность + валидность basic-кредов
    (``GET IAssignments?$top=1``). Побочных эффектов нет — сообщения не шлём."""
    row = await _load_singleton(db)
    if not directum_configured(row):
        return DirectumTestResult(ok=False, error="Credentials are not configured")

    password = decrypt_secret(row.auth_password_enc)  # type: ignore[arg-type]
    try:
        count = await ping(
            base_url=row.base_url, username=row.auth_username or "", password=password
        )
    except DirectumApiError as exc:
        logger.warning(
            "directum.test_failed",
            status=getattr(exc, "status_code", None),
            by=str(admin.id),
        )
        status_code = getattr(exc, "status_code", None)
        hint = "See server logs for details."
        if status_code in (401, 403):
            hint = "Authentication failed — check the service account login/password."
        elif status_code is None:
            hint = "Directum unreachable (DNS/TLS/network). Check base_url."
        return DirectumTestResult(
            ok=False,
            error=f"Directum OData request failed (HTTP {status_code}). {hint}",
        )

    return DirectumTestResult(
        ok=True,
        detail=(
            f"Подключение к {row.base_url} работает, креды валидны "
            f"(пробный запрос вернул записей: {count})."
        ),
    )
