"""Mailing recipients directory API (docs/wip/news-email-share.md).

A curated address book used by the news "share by email" feature. Both reads
(for the share-modal dropdown) and mutations require ``editor``/``admin`` via
:data:`EditorDep`. Every mutation emits an audit event after commit.
"""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, EditorDep, RedisDep
from app.core.logging import get_logger
from app.schemas.mailing_recipient import (
    CreateMailingRecipientRequest,
    MailingRecipientList,
    MailingRecipientPublic,
    UpdateMailingRecipientRequest,
)
from app.services import mailing_recipients as svc
from app.services.audit import make_audit_emitter

router = APIRouter(prefix="/mailing-recipients", tags=["mailing-recipients"])
logger = get_logger(__name__)

_emit_audit = make_audit_emitter("mailing_recipient")


@router.get("", response_model=MailingRecipientList, summary="Список получателей рассылки (editor)")
async def list_recipients(
    editor: EditorDep,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MailingRecipientList:
    items, total = await svc.list_recipients(db, q=q, limit=limit, offset=offset)
    return MailingRecipientList(
        items=[MailingRecipientPublic.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=MailingRecipientPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать получателя рассылки (editor)",
)
async def create_recipient(
    body: CreateMailingRecipientRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> MailingRecipientPublic:
    recipient = await svc.create_recipient(db, body, editor.id)
    await _emit_audit(
        redis,
        event_type="mailing_recipients.created",
        user_id=str(editor.id),
        resource_id=str(recipient.id),
        resource_title=recipient.name,
    )
    logger.info("mailing_recipient.created", recipient_id=str(recipient.id), editor=str(editor.id))
    return cast(MailingRecipientPublic, MailingRecipientPublic.model_validate(recipient))


@router.put(
    "/{recipient_id}",
    response_model=MailingRecipientPublic,
    summary="Обновить получателя рассылки (editor)",
)
async def update_recipient(
    recipient_id: uuid.UUID,
    body: UpdateMailingRecipientRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> MailingRecipientPublic:
    recipient = await svc.get_recipient_or_404(db, recipient_id)
    changed = await svc.update_recipient(db, recipient, body)
    await _emit_audit(
        redis,
        event_type="mailing_recipients.updated",
        user_id=str(editor.id),
        resource_id=str(recipient.id),
        resource_title=recipient.name,
        metadata={"fields": changed},
    )
    logger.info("mailing_recipient.updated", recipient_id=str(recipient.id), editor=str(editor.id))
    return cast(MailingRecipientPublic, MailingRecipientPublic.model_validate(recipient))


@router.delete(
    "/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить получателя рассылки (editor, soft)",
)
async def delete_recipient(
    recipient_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    recipient = await svc.get_recipient_or_404(db, recipient_id)
    await svc.soft_delete_recipient(db, recipient)
    await _emit_audit(
        redis,
        event_type="mailing_recipients.deleted",
        user_id=str(editor.id),
        resource_id=str(recipient_id),
        resource_title=recipient.name,
    )
    logger.info("mailing_recipient.deleted", recipient_id=str(recipient_id), editor=str(editor.id))
