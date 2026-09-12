"""Документы на согласование: список, карточка, вложения, действия.

Права доступа: любой авторизованный сотрудник (решение владельца,
2026-09-04) — реальную видимость документов определяет 1С: список
``DocumentsForApproval`` фильтрован по токену пользователя, а карточка и
действия ищут документ только **в этом списке** (GUID чужого документа →
404 ещё на стороне портала; после пакета доработок 1С перепроверяет токен
на своей стороне — двойной барьер).

Массовое согласование — строго последовательно с паузой (совет
1С-разработчика: каждый GETAgreed проводит документ и запускает фоновое
задание; параллелить нельзя).
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.approvals._common import (
    _configured_auth,
    _load_settings_singleton,
    _map_erp_error,
)
from app.api.deps import CurrentUser, DbDep, RedisDep, require_approvals_module
from app.api.kb._common import _rfc5987_filename
from app.core.logging import get_logger
from app.core.metrics import approvals_actions_total
from app.core.uploads import magic
from app.models.approvals import ApprovalsSettings
from app.schemas.approvals import (
    ActionOut,
    ApprovalAttachmentInfo,
    ApprovalDocument,
    ApprovalDocumentDetail,
    ApprovalDocumentList,
    ApproveIn,
    BulkApproveIn,
    BulkApproveItemResult,
    BulkApproveOut,
    RejectIn,
)
from app.services.approvals import client
from app.services.approvals.client import ErpApprovalsError, ErpTransportError
from app.services.audit import push_audit_event

logger = get_logger(__name__)

# Сырая функция, НЕ Annotated-алиас: Depends(Annotated-алиас) в router-level
# dependencies в FastAPI 0.140 генерирует фантомные обязательные query-параметры
# args/kwargs (endpoint отвечает 422 на любой запрос; клон directum-паттерна).
router = APIRouter(dependencies=[Depends(require_approvals_module)])

# Внутренние заказы исключены из массового согласования: по каждому нужен
# свой выбор ответственного (v2.1.0.0: Employee из Пользователи[]; в партии
# выбрать ответственного нельзя). Сами по себе они согласуются — 409-гейт
# снят (решение владельца 2026-09-06; до этого были «информационно»).
INTERNAL_BULK_SKIP = "Внутренний заказ согласуется по одному — в карточке документа"


async def _own_document(
    db: DbDep, redis: RedisDep, user_email: str, guid: str
) -> tuple[ApprovalsSettings, str, str, tuple[str, str], ApprovalDocument]:
    """Документ из списка текущего пользователя (владелец = видит в списке).
    Возвращает (row, base_url, token_base_url, auth, document)."""
    row = await _load_settings_singleton(db)
    base_url, token_base_url, auth = _configured_auth(row)
    try:
        documents = await client.get_documents(base_url, token_base_url, auth, user_email, redis)
    except ErpApprovalsError as exc:
        raise _map_erp_error(exc) from exc
    for doc in documents:
        if doc.guid == guid:
            return row, base_url, token_base_url, auth, doc
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")


@router.get("", response_model=ApprovalDocumentList)
async def list_documents(db: DbDep, redis: RedisDep, user: CurrentUser) -> ApprovalDocumentList:
    row = await _load_settings_singleton(db)
    base_url, token_base_url, auth = _configured_auth(row)
    try:
        items = await client.get_documents(base_url, token_base_url, auth, user.email, redis)
    except ErpApprovalsError as exc:
        raise _map_erp_error(exc) from exc
    return ApprovalDocumentList(items=items, total=len(items))


@router.get("/{document_uuid}", response_model=ApprovalDocumentDetail)
async def get_document(
    document_uuid: str, db: DbDep, redis: RedisDep, user: CurrentUser
) -> ApprovalDocumentDetail:
    _, base_url, token_base_url, auth, doc = await _own_document(
        db, redis, user.email, document_uuid
    )
    try:
        entries = await client.get_attachments(
            base_url, token_base_url, auth, user.email, document_uuid, redis
        )
    except ErpApprovalsError as exc:
        raise _map_erp_error(exc) from exc
    attachments = [
        ApprovalAttachmentInfo(index=index, name=client.attachment_name(entry))
        for index, entry in enumerate(entries)
    ]
    return ApprovalDocumentDetail(**doc.model_dump(), attachments=attachments)


@router.get("/{document_uuid}/attachments/{index}")
async def download_attachment(
    document_uuid: str,
    index: int,
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
) -> Response:
    """Вложение документа: base64 из 1С декодируется и отдаётся стримом,
    на диск ничего не пишется (анти-паттерн старого PHP: files/ + 0777).
    Владение документом проверяет 1С по токену (пакет доработок)."""
    row = await _load_settings_singleton(db)
    base_url, token_base_url, auth = _configured_auth(row)
    try:
        filename, data = await client.get_attachment_file(
            base_url, token_base_url, auth, user.email, document_uuid, index, redis
        )
    except ErpApprovalsError as exc:
        raise _map_erp_error(exc) from exc
    logger.info(
        "approvals.attachment_downloaded",
        document=document_uuid,
        index=index,
        filename=filename,
        user_id=str(user.id),
    )
    media_type = "application/octet-stream"
    if magic is not None:
        with contextlib.suppress(Exception):  # не угадали MIME → отдаём как есть
            media_type = magic.from_buffer(data[:2048], mime=True) or media_type
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": _rfc5987_filename(filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{document_uuid}/approve", response_model=ActionOut)
async def approve_document(
    document_uuid: str,
    payload: ApproveIn,
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
) -> ActionOut:
    _, base_url, token_base_url, auth, doc = await _own_document(
        db, redis, user.email, document_uuid
    )
    # Внутренние заказы согласуются в общем потоке: 1С (v2.1.0.0) сама запишет
    # Employee из Пользователи[] ответственным и завершит этап. Если документ
    # requires_manager — generic-проверка ниже потребует manager_guid и
    # проверит, что он из списка документа.
    if doc.requires_manager:
        if not payload.manager_guid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Для этого документа нужно выбрать ответственного",
            )
        if payload.manager_guid not in {m.guid for m in doc.managers}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Выбранный ответственный не входит в список документа",
            )
    try:
        message = await client.approve(
            base_url,
            token_base_url,
            auth,
            user.email,
            document_uuid,
            comment=payload.comment,
            employee_guid=payload.manager_guid,
            redis=redis,
        )
    except ErpApprovalsError as exc:
        approvals_actions_total.labels(action="approve", outcome="error").inc()
        raise _map_erp_error(exc) from exc
    approvals_actions_total.labels(action="approve", outcome="ok").inc()
    logger.info(
        "approvals.approved",
        document=document_uuid,
        doc_type=doc.doc_type,
        number=doc.number,
        user_id=str(user.id),
    )
    await push_audit_event(
        redis,
        event_type="approvals.approved",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="approval_document",
        resource_id=document_uuid,
        metadata={"doc_type": doc.doc_type, "number": doc.number},
    )
    return ActionOut(ok=True, message=message)


@router.post("/{document_uuid}/reject", response_model=ActionOut)
async def reject_document(
    document_uuid: str,
    payload: RejectIn,
    db: DbDep,
    redis: RedisDep,
    user: CurrentUser,
) -> ActionOut:
    _, base_url, token_base_url, auth, doc = await _own_document(
        db, redis, user.email, document_uuid
    )
    try:
        message = await client.reject(
            base_url,
            token_base_url,
            auth,
            user.email,
            document_uuid,
            comment=payload.comment,
            redis=redis,
        )
    except ErpApprovalsError as exc:
        approvals_actions_total.labels(action="reject", outcome="error").inc()
        raise _map_erp_error(exc) from exc
    approvals_actions_total.labels(action="reject", outcome="ok").inc()
    logger.info(
        "approvals.rejected",
        document=document_uuid,
        doc_type=doc.doc_type,
        number=doc.number,
        user_id=str(user.id),
    )
    await push_audit_event(
        redis,
        event_type="approvals.rejected",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="approval_document",
        resource_id=document_uuid,
        metadata={"doc_type": doc.doc_type, "number": doc.number},
    )
    return ActionOut(ok=True, message=message)


@router.post("/bulk-approve", response_model=BulkApproveOut)
async def bulk_approve(
    payload: BulkApproveIn, db: DbDep, redis: RedisDep, user: CurrentUser
) -> BulkApproveOut:
    row = await _load_settings_singleton(db)
    base_url, token_base_url, auth = _configured_auth(row)
    try:
        documents = await client.get_documents(base_url, token_base_url, auth, user.email, redis)
    except ErpApprovalsError as exc:
        raise _map_erp_error(exc) from exc
    by_guid = {doc.guid: doc for doc in documents}

    results: list[BulkApproveItemResult] = []
    for position, guid in enumerate(payload.uuids):
        if position > 0:
            # Пауза между тяжёлыми вызовами (проведение документа в 1С).
            await asyncio.sleep(client.BULK_APPROVE_PAUSE_SECONDS)
        doc = by_guid.get(guid)
        if doc is None:
            results.append(BulkApproveItemResult(uuid=guid, ok=False, message="Документ не найден"))
            continue
        if doc.requires_manager:
            results.append(
                BulkApproveItemResult(
                    uuid=guid,
                    ok=False,
                    message="Требуется выбрать ответственного (согласуйте по одному)",
                )
            )
            continue
        if not doc.has_prices:
            results.append(BulkApproveItemResult(uuid=guid, ok=False, message=INTERNAL_BULK_SKIP))
            continue
        try:
            message = await client.approve(
                base_url, token_base_url, auth, user.email, guid, redis=redis
            )
            results.append(BulkApproveItemResult(uuid=guid, ok=True, message=message))
        except ErpTransportError as exc:
            # Транспортный сбой (таймаут/обрыв): ERP недоступна — продолжать
            # партию бессмысленно, помечаем хвост «не обрабатывался» и
            # возвращаем частичный отчёт как обычно (ревью 2026-09-05: сырой
            # httpx-эксепшн сюда не долетал и ронял запрос в 500, теряя
            # результаты уже согласованных документов). После таймаута
            # проведение в 1С могло всё же пройти — честно предупреждаем.
            message = str(exc)
            if isinstance(exc.__cause__, httpx.TimeoutException):
                message += " — проведение в 1С могло пройти, проверьте документ"
            results.append(BulkApproveItemResult(uuid=guid, ok=False, message=message))
            for remaining in payload.uuids[position + 1 :]:
                results.append(
                    BulkApproveItemResult(
                        uuid=remaining,
                        ok=False,
                        message="ERP недоступна — документ не обрабатывался",
                    )
                )
            break
        except ErpApprovalsError as exc:
            results.append(BulkApproveItemResult(uuid=guid, ok=False, message=str(exc)))

    approved = sum(1 for r in results if r.ok)
    failed = len(results) - approved
    if not approved:
        outcome = "error"
    elif failed:
        outcome = "partial"
    else:
        outcome = "ok"
    approvals_actions_total.labels(action="bulk_approve", outcome=outcome).inc()
    logger.info(
        "approvals.bulk_approved",
        requested=len(payload.uuids),
        approved=approved,
        failed=failed,
        user_id=str(user.id),
    )
    await push_audit_event(
        redis,
        event_type="approvals.bulk_approved",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="approval_document",
        resource_id="bulk",
        metadata={"approved": approved, "failed": failed, "uuids": list(payload.uuids)},
    )
    return BulkApproveOut(results=results, approved=approved, failed=failed)
