"""Email-signature generator API (docs/wip/signature.md).

Stateless module ported from the legacy PHP service ``./sign``. Master-flag
gated via ``modules.json`` (``signature.enabled``): when off, the whole section
returns 404. Read/generate endpoints are open to any authenticated user;
settings are admin-only and audited.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.api.deps import AdminDep, CurrentUser, RedisDep
from app.core.logging import get_logger
from app.core.modules_config import load_modules_shared
from app.schemas.signature import (
    SignatureConfigResponse,
    SignatureGenerateRequest,
    SignatureGenerateResponse,
    SignatureSettings,
    SignatureSettingsIn,
)
from app.services import signature as svc
from app.services.audit import make_audit_emitter
from app.services.signature_settings import load_signature_settings, save_signature_settings

router = APIRouter(prefix="/signature", tags=["signature"])
logger = get_logger(__name__)

_emit_audit = make_audit_emitter("signature")


async def _require_module_enabled(redis: RedisDep) -> None:
    modules = await load_modules_shared(redis)
    if not modules.signature.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature disabled")


@router.get("/config", response_model=SignatureConfigResponse, summary="Данные для формы")
async def get_config(user: CurrentUser, redis: RedisDep) -> SignatureConfigResponse:
    await _require_module_enabled(redis)
    s = load_signature_settings()
    return SignatureConfigResponse(
        cities=s.cities,
        office_phones=s.office_phones,
        support_email=s.support_email,
        prefill=svc.build_prefill(
            full_name=user.full_name,
            lang=user.lang,
            position=user.position,
            email=user.email,
            attributes=user.attributes,
            settings=s,
        ),
    )


@router.post("/generate", response_model=SignatureGenerateResponse, summary="Сгенерировать подпись")
async def generate(
    body: SignatureGenerateRequest,
    _: CurrentUser,
    redis: RedisDep,
) -> SignatureGenerateResponse:
    await _require_module_enabled(redis)
    return svc.render_signature(body, load_signature_settings())


@router.post("/download", summary="Скачать подпись (.htm)")
async def download(
    body: SignatureGenerateRequest,
    _: CurrentUser,
    redis: RedisDep,
) -> Response:
    await _require_module_enabled(redis)
    result = svc.render_signature(body, load_signature_settings())
    disposition = (
        f"attachment; filename=\"signature.htm\"; filename*=UTF-8''{quote(result.filename)}"
    )
    return Response(
        content=result.html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "no-store, max-age=0",
        },
    )


# ── Admin settings ───────────────────────────────────────────────────────────


@router.get("/admin/settings", response_model=SignatureSettings, summary="Настройки (admin)")
async def get_settings(_: AdminDep, redis: RedisDep) -> SignatureSettings:
    await _require_module_enabled(redis)
    return load_signature_settings()


@router.put(
    "/admin/settings",
    response_model=SignatureSettings,
    summary="Обновить настройки (admin)",
)
async def update_settings(
    body: SignatureSettingsIn,
    admin: AdminDep,
    redis: RedisDep,
) -> SignatureSettings:
    await _require_module_enabled(redis)
    settings = SignatureSettings(
        cities=body.cities,
        office_phones=body.office_phones,
        support_email=body.support_email,
        company_url=body.company_url,
        logo_base_url=body.logo_base_url,
        attr_mobile=body.attr_mobile,
        attr_office_phone=body.attr_office_phone,
        attr_city=body.attr_city,
    )
    save_signature_settings(settings)
    await _emit_audit(
        redis,
        event_type="signature.settings_updated",
        user_id=str(admin.id),
        resource_id="signature",
    )
    logger.info("signature.settings_updated", admin=str(admin.id))
    return settings
