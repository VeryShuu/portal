from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbDep, EditorDep, RedisDep
from app.core.logging import get_logger
from app.schemas.links import (
    CreateLinkRequest,
    ReorderLinksRequest,
    ServiceLinkList,
    ServiceLinkPublic,
    UpdateLinkRequest,
)
from app.services import link_icon, links_crud, links_query, links_sso
from app.services.audit import push_audit_event

router = APIRouter(prefix="/links", tags=["links"])
logger = get_logger(__name__)


async def _emit_link_audit(
    redis: RedisDep,
    *,
    event_type: str,
    user_id: str,
    resource_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await push_audit_event(
        redis,
        event_type=event_type,
        user_id=user_id,
        resource_type="link",
        resource_id=resource_id,
        metadata=metadata,
    )


@router.get("", response_model=ServiceLinkList, summary="Список ярлыков")
async def list_links(
    user: CurrentUser,
    db: DbDep,
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    orphaned: bool = Query(default=False),
) -> ServiceLinkList:
    hidden_ids: list[str] = user.preferences.get("hidden_link_ids", [])
    conditions = links_query.build_link_conditions(
        include_inactive=include_inactive,
        category=category,
        orphaned=orphaned,
        is_admin=user.role == "admin",
    )
    items, total = await links_query.list_service_links(db, conditions, hidden_ids)
    return ServiceLinkList(
        items=[ServiceLinkPublic.model_validate(item) for item in items],
        total=total,
    )


@router.patch(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Изменить порядок ярлыков (admin)",
)
async def reorder_links(
    body: ReorderLinksRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    if not body.items:
        return

    await links_crud.reorder_links(db, body.items)
    await _emit_link_audit(
        redis,
        event_type="links.reordered",
        user_id=str(editor.id),
        resource_id=None,
        metadata={"count": len(body.items)},
    )
    logger.info("link.reordered", editor=str(editor.id), count=len(body.items))


@router.get("/{link_id}", response_model=ServiceLinkPublic, summary="Получить ярлык")
async def get_link(link_id: uuid.UUID, user: CurrentUser, db: DbDep) -> ServiceLinkPublic:
    link = await links_crud.get_link_or_404(db, link_id)
    return ServiceLinkPublic.model_validate(link)


@router.get("/{link_id}/sso-redirect", summary="Серверный SSO-редирект для ярлыка")
async def sso_redirect(
    link_id: uuid.UUID,
    _user: CurrentUser,
    db: DbDep,
    request: Request,
    redis: RedisDep,
) -> RedirectResponse:
    """302-редирект на целевой сервис с id_token_hint.

    id_token_hint НЕ возвращается клиенту в теле ответа — только через Location-заголовок
    сервера, что исключает попадание токена в историю браузера портала и JS-память.
    """
    link = await links_crud.get_link_or_404(db, link_id)
    if not link.supports_sso:
        return RedirectResponse(url=link.url, status_code=302)

    url = await links_sso.build_sso_url(link.url, request, redis)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{link_id}/sso-url", summary="SSO URL для ярлыка (устарел, используйте sso-redirect)")
async def get_sso_url(
    link_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    request: Request,
    redis: RedisDep,
) -> dict[str, str]:
    """Оставлен для обратной совместимости. Предпочтительный вариант — sso-redirect."""
    link = await links_crud.get_link_or_404(db, link_id)
    if not link.supports_sso:
        return {"url": link.url}

    url = await links_sso.build_sso_url(link.url, request, redis)
    return {"url": url, "sso": True}  # type: ignore[dict-item]


@router.post(
    "",
    response_model=ServiceLinkPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Создать ярлык (admin)",
)
async def create_link(
    body: CreateLinkRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    link = await links_crud.create_link(db, body, editor.id)
    await _emit_link_audit(
        redis,
        event_type="links.created",
        user_id=str(editor.id),
        resource_id=str(link.id),
    )
    logger.info("link.created", link_id=str(link.id), editor=str(editor.id))
    return ServiceLinkPublic.model_validate(link)


@router.put("/{link_id}", response_model=ServiceLinkPublic, summary="Обновить ярлык (admin)")
async def update_link(
    link_id: uuid.UUID,
    body: UpdateLinkRequest,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    link = await links_crud.get_link_or_404(db, link_id)
    changed_fields = await links_crud.update_link(db, link, body)
    await _emit_link_audit(
        redis,
        event_type="links.updated",
        user_id=str(editor.id),
        resource_id=str(link.id),
        metadata={"fields": changed_fields},
    )
    logger.info("link.updated", link_id=str(link.id), editor=str(editor.id))
    return ServiceLinkPublic.model_validate(link)


@router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ярлык (admin)",
)
async def delete_link(
    link_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    link = await links_crud.get_link_or_404(db, link_id)
    link_icon.remove_icon_files(link_id)
    await links_crud.delete_link(db, link)
    await _emit_link_audit(
        redis,
        event_type="links.deleted",
        user_id=str(editor.id),
        resource_id=str(link_id),
    )
    logger.info("link.deleted", link_id=str(link_id), editor=str(editor.id))


@router.post(
    "/{link_id}/icon",
    response_model=ServiceLinkPublic,
    summary="Загрузить иконку ярлыка (admin)",
)
async def upload_link_icon(
    link_id: uuid.UUID,
    file: UploadFile,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> ServiceLinkPublic:
    link = await links_crud.get_link_or_404(db, link_id)
    icon_url = await link_icon.save_link_icon(file, link_id)
    await links_crud.set_icon_url(db, link_id, icon_url)
    await db.refresh(link)
    await _emit_link_audit(
        redis,
        event_type="links.updated",
        user_id=str(editor.id),
        resource_id=str(link_id),
        metadata={"fields": ["icon_url"]},
    )
    logger.info("link.icon.uploaded", link_id=str(link_id), editor=str(editor.id))
    return ServiceLinkPublic.model_validate(link)


@router.delete(
    "/{link_id}/icon",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить иконку ярлыка (admin)",
)
async def delete_link_icon(
    link_id: uuid.UUID,
    editor: EditorDep,
    db: DbDep,
    redis: RedisDep,
) -> None:
    await links_crud.get_link_or_404(db, link_id)
    link_icon.remove_icon_files(link_id)
    await links_crud.set_icon_url(db, link_id, None)
    await _emit_link_audit(
        redis,
        event_type="links.updated",
        user_id=str(editor.id),
        resource_id=str(link_id),
        metadata={"fields": ["icon_url"]},
    )
    logger.info("link.icon.deleted", link_id=str(link_id), editor=str(editor.id))
