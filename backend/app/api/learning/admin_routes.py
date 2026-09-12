"""Администрирование учёток обучения — эндпоинты методиста.

Только внутренний контур (портал): гейт ``require_learning_admin`` +
мастер-переключатель модуля. Все мутации пишут audit-события (правило проекта).
Учётки passwordless (миграция 113): паролей нет; запасной путь «письмо с кодом
не дошло» — ручная выдача кода (plaintext только в ответе этого API).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import LearningAdminDep, LearningDbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.models.learning import LearningAccount
from app.schemas.learning import (
    LearningAccountCreate,
    LearningAccountImportError,
    LearningAccountImportOut,
    LearningAccountListOut,
    LearningAccountOut,
    LearningLoginCodeOut,
)
from app.services.audit import push_audit_event
from app.services.learning import account_import
from app.services.learning import accounts_service as svc

router = APIRouter(
    prefix="/learning/admin/accounts",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _get_or_404(db: LearningDbDep, account_id: uuid.UUID) -> LearningAccount:
    account = await svc.get_active_by_id(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Учётка не найдена")
    return account


@router.post(
    "",
    summary="Создать учётку (без пароля — вход по коду из письма)",
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    body: LearningAccountCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> LearningAccountOut:
    account = await svc.create_account(
        db,
        email=body.email,
        full_name=body.full_name,
        department=body.department,
        position=body.position,
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.account_created",
        user_id=str(admin.id),
        resource_type="learning_account",
        resource_id=str(account.id),
        resource_title=account.full_name,
        ip_address=_client_ip(request),
    )
    return LearningAccountOut.model_validate(account)


@router.get("/template", summary="Скачать шаблон импорта учёток")
async def download_import_template(_admin: LearningAdminDep) -> Response:
    return Response(
        content=account_import.build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="learning-accounts-template.xlsx"',
            "Cache-Control": "no-store, max-age=0",
        },
    )


@router.post("/import", summary="Импортировать учётки из xlsx")
async def import_accounts(
    file: UploadFile,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> LearningAccountImportOut:
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Допустим только файл .xlsx")
    data = await file.read(account_import.MAX_IMPORT_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Файл пуст")
    if len(data) > account_import.MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Файл больше 5 МБ")
    try:
        parsed = account_import.parse_xlsx(data)
    except account_import.ImportFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    result = await account_import.import_accounts(db, parsed)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.accounts_imported",
        user_id=str(admin.id),
        resource_type="learning_account",
        ip_address=_client_ip(request),
        metadata={
            "created": result.created,
            "skipped_duplicates": result.skipped_duplicates,
            "error_count": len(result.errors),
        },
    )
    return LearningAccountImportOut(
        created=result.created,
        skipped_duplicates=result.skipped_duplicates,
        error_count=len(result.errors),
        errors=[
            LearningAccountImportError(row=error.row_number, message=error.message)
            for error in result.errors
        ],
    )


@router.get("", summary="Список учёток (поиск + пагинация)")
async def list_accounts(
    _admin: LearningAdminDep,
    db: LearningDbDep,
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LearningAccountListOut:
    base = select(LearningAccount).where(LearningAccount.deleted_at.is_(None))
    count_base = (
        select(func.count())
        .select_from(LearningAccount)
        .where(LearningAccount.deleted_at.is_(None))
    )
    if q:
        pattern = f"%{q.strip().lower()}%"
        cond = func.lower(LearningAccount.full_name).like(pattern) | func.lower(
            LearningAccount.email
        ).like(pattern)
        base = base.where(cond)
        count_base = count_base.where(cond)

    total = (await db.execute(count_base)).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(LearningAccount.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return LearningAccountListOut(
        items=[LearningAccountOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{account_id}/login-code", summary="Выдать код входа вручную")
async def issue_login_code(
    account_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> LearningLoginCodeOut:
    """Запасной путь «письмо с кодом не дошло»: админ выпускает код и передаёт
    его человеку по телефону/мессенджеру. Код одноразовый, живёт минуты
    (learning_code_ttl_minutes); plaintext — только в этом ответе."""
    account = await _get_or_404(db, account_id)
    code, expires_at = await svc.issue_manual_code(db, account=account)
    await push_audit_event(
        redis,
        event_type="learning.login_code_issued",
        user_id=str(admin.id),
        resource_type="learning_account",
        resource_id=str(account.id),
        resource_title=account.full_name,
        ip_address=_client_ip(request),
    )
    return LearningLoginCodeOut(code=code, expires_at=expires_at)


@router.post("/{account_id}/block", summary="Постоянно заблокировать учётку")
async def block_account(
    account_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    account = await _get_or_404(db, account_id)
    if account.status == "blocked":
        return {"ok": True}
    await svc.admin_set_status(db, redis, account, blocked=True)
    await push_audit_event(
        redis,
        event_type="learning.account_blocked",
        user_id=str(admin.id),
        resource_type="learning_account",
        resource_id=str(account.id),
        resource_title=account.full_name,
        ip_address=_client_ip(request),
    )
    return {"ok": True}


@router.post("/{account_id}/unblock", summary="Разблокировать учётку")
async def unblock_account(
    account_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    account = await _get_or_404(db, account_id)
    if account.status != "blocked":
        return {"ok": True}
    await svc.admin_set_status(db, redis, account, blocked=False)
    await push_audit_event(
        redis,
        event_type="learning.account_unblocked",
        user_id=str(admin.id),
        resource_type="learning_account",
        resource_id=str(account.id),
        resource_title=account.full_name,
        ip_address=_client_ip(request),
    )
    return {"ok": True}
