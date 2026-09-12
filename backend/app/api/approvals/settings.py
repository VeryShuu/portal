"""Settings CRUD модуля согласования (singleton ``approvals_settings``).

Клон :mod:`app.api.directum.settings`: пароль write-only (Fernet,
``auth_password_enc``), в ответе только ``password_set``; пустой пароль в
PUT = «оставить прежний». ``POST /approvals/test`` — проверка доступности ERP
и принятия Basic-кредов (без побочных эффектов).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.approvals._common import _load_settings_singleton, _settings_to_out
from app.api.deps import AdminDep, DbDep, RedisDep, require_approvals_module
from app.core.logging import get_logger
from app.core.secret_crypto import encrypt_secret
from app.schemas.approvals import ApprovalsSettingsIn, ApprovalsSettingsOut, ApprovalsTestResult
from app.services.approvals import client
from app.services.approvals.settings import decrypt_password
from app.services.audit import push_audit_event

logger = get_logger(__name__)

# Сырая функция, НЕ Annotated-алиас: Depends(Annotated-алиас) в router-level
# dependencies в FastAPI 0.140 генерирует фантомные обязательные query-параметры
# args/kwargs (endpoint отвечает 422 на любой запрос; клон directum-паттерна).
router = APIRouter(dependencies=[Depends(require_approvals_module)])


@router.get("/settings", response_model=ApprovalsSettingsOut)
async def get_settings(_admin: AdminDep, db: DbDep) -> ApprovalsSettingsOut:
    return _settings_to_out(await _load_settings_singleton(db))


@router.put("/settings", response_model=ApprovalsSettingsOut)
async def put_settings(
    payload: ApprovalsSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> ApprovalsSettingsOut:
    row = await _load_settings_singleton(db)
    row.updated_by_user_id = admin.id
    row.base_url = payload.base_url
    row.token_base_url = payload.token_base_url or None
    row.auth_username = payload.auth_username
    if payload.auth_password:  # write-only: пусто/None = оставить прежний шифр
        row.auth_password_enc = encrypt_secret(payload.auth_password)

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="approvals.settings_updated",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="approvals_settings",
        resource_id="1",
        metadata={"password_changed": bool(payload.auth_password)},
    )
    logger.info("approvals.settings_updated", by=str(admin.id))
    return _settings_to_out(row)


@router.post("/test", response_model=ApprovalsTestResult)
async def check_connection(admin: AdminDep, db: DbDep) -> ApprovalsTestResult:
    """Проверка подключения: GETTokenByLogin с email самого админа — WAF,
    креды Portal, сервис и маппинг логина. Побочных эффектов нет (токен
    просто живёт 30 минут в регистре 1С)."""
    row = await _load_settings_singleton(db)
    if not (row.base_url and row.auth_username and row.auth_password_enc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Настройки не заполнены: нужны base_url, учётка и пароль",
        )
    password = decrypt_password(row)
    if not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль не расшифровывается — сохраните его заново",
        )
    token_base_url = (row.token_base_url or "").strip() or row.base_url
    ok, message, latency_ms = await client.ping(
        row.base_url, token_base_url, (row.auth_username, password), admin.email
    )
    logger.info("approvals.connection_test", ok=ok, latency_ms=latency_ms)
    return ApprovalsTestResult(ok=ok, message=message, latency_ms=latency_ms)
