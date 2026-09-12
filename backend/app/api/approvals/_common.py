"""Общие хелперы роутеров модуля согласования (settings/documents)."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.api.deps import DbDep
from app.core.logging import get_logger
from app.models.approvals import ApprovalsSettings
from app.schemas.approvals import ApprovalsSettingsOut
from app.services.approvals import client
from app.services.approvals.settings import (
    decrypt_password,
    is_configured,
    load_approvals_settings,
)

logger = get_logger(__name__)


async def _load_settings_singleton(db: DbDep) -> ApprovalsSettings:
    """Singleton всегда существует (миграция 115); защитно создаём."""
    row = await load_approvals_settings(db)
    if row is None:
        row = ApprovalsSettings(id=1)
        db.add(row)
        await db.flush()
    return row


def _settings_to_out(row: ApprovalsSettings) -> ApprovalsSettingsOut:
    return ApprovalsSettingsOut(
        base_url=row.base_url,
        token_base_url=(row.token_base_url or "").strip(),
        auth_username=row.auth_username,
        password_set=bool(row.auth_password_enc),
        configured=is_configured(row),
        updated_at=row.updated_at,
    )


def _configured_auth(row: ApprovalsSettings) -> tuple[str, str, tuple[str, str]]:
    """(base_url, token_base_url, basic_auth) из настроек; не настроено →
    503 «не настроен» (пользователь понимает: бежать к админу, а не сообщать
    об ошибке). token_base_url пуст/NULL → как base_url (до миграционного
    бэкфилла и для старых записей)."""
    password = decrypt_password(row)
    if not is_configured(row) or password is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Модуль согласования не настроен (обратитесь к администратору)",
        )
    token_base_url = (row.token_base_url or "").strip() or row.base_url
    return row.base_url, token_base_url, (row.auth_username, password)


def _map_erp_error(exc: client.ErpApprovalsError) -> HTTPException:
    """Ошибки 1С → HTTP портала. Транспорт/неизвестное — 502 (upstream);
    «не ваш документ» (403) и «не найден» (404) — как есть: пользователь
    должен понимать отказ ERP, а не видеть «ошибку портала»."""
    code = exc.status_code
    if code == status.HTTP_400_BAD_REQUEST:
        # Карта ошибок 1С: 400 = нет обязательного параметра / Employee не в
        # группе «Ответственные за закупку» — юзер-экшенабельная, показываем.
        return HTTPException(status_code=400, detail=str(exc))
    if code == status.HTTP_403_FORBIDDEN:
        # «Документ не в очереди» — в т.ч. дабл-клик; 1С формулирует мягко.
        return HTTPException(status_code=403, detail=str(exc))
    if code == status.HTTP_404_NOT_FOUND:
        # В т.ч. «логин не сопоставлен» (покрытие регистра 177/N) — мягкий текст.
        return HTTPException(status_code=404, detail=str(exc))
    # 5xx / транспорт / неразборчивый ответ — реальная проблема доступности:
    # фиксируем в логах (Loki) с усечённым текстом 1С; 400/403/404 выше —
    # штатные пользовательские ситуации, не шумим.
    logger.warning("approvals.erp_error", status=code, detail=str(exc)[:300])
    return HTTPException(status_code=502, detail=f"Ошибка ERP: {exc}")
