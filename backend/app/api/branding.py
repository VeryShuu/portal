"""Branding & email-settings API.

Thin HTTP layer over ``app.services.branding_assets`` (portal settings + image
assets) and ``app.services.email_settings`` (SMTP config + test email). Handlers
do ACL, delegate to the services and emit audit events.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from redis.asyncio import Redis

from app.api.deps import AdminDep, CurrentUser, EditorDep, RedisDep
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.schemas.branding import (
    BrandingSettings,
    BrandingSettingsOut,
    EmailSettings,
    EmailSettingsIn,
    EmailSettingsOut,
    EmailTestRequest,
)
from app.services import branding_assets, email_settings
from app.services.audit import make_audit_emitter

logger = get_logger(__name__)

_emit_audit = make_audit_emitter("branding")

router = APIRouter(tags=["branding"])

_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
_CACHE_SHORT = "public, max-age=3600"


async def _audit(redis: Redis, user_id: str, target: str) -> None:
    await _emit_audit(
        redis,
        event_type="branding.updated",
        user_id=user_id,
        metadata={"target": target},
    )


def _serve_asset(
    request: Request,
    prefix: str,
    exts: list[str],
    *,
    default_mime: str,
    cache_control: str,
    not_found: str,
) -> Response:
    f = branding_assets.find_file(prefix, exts)
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)
    mime = branding_assets.EXT_TO_MIME.get(f.suffix, default_mime)
    if request.method == "HEAD":
        return Response(headers={"Content-Type": mime, "Cache-Control": cache_control})
    return FileResponse(f, media_type=mime, headers={"Cache-Control": cache_control})


async def _upload_asset(
    file: UploadFile,
    redis: Redis,
    user_id: str,
    *,
    prefix: str,
    exts: list[str],
    mime_map: dict[str, str],
    label: str,
    target: str,
) -> dict:
    url = await branding_assets.upload_image(file, prefix, exts, mime_map, label)
    await _audit(redis, user_id, target)
    return {"url": url}


async def _reset_asset(
    redis: Redis,
    user_id: str,
    *,
    prefix: str,
    exts: list[str],
    target: str,
    detail: str,
    log_key: str,
) -> dict:
    branding_assets.delete_files(prefix, exts)
    await _audit(redis, user_id, target)
    logger.info(log_key)
    return {"detail": detail}


# ── Settings ─────────────────────────────────────────────────────────────────


@router.get("/branding/settings", summary="Настройки оформления портала")
async def get_settings() -> BrandingSettingsOut:
    s = branding_assets.load_settings()
    sys = load_system_settings()
    iframe_origins: list[str] = []
    if sys.video_gallery_url:
        iframe_origins.append(sys.video_gallery_url)
    logo_file = branding_assets.find_file("logo", branding_assets.ALL_EXTS)
    logo_updated_at = str(int(logo_file.stat().st_mtime)) if logo_file else None
    return BrandingSettingsOut(
        **s.model_dump(),
        has_favicon=branding_assets.find_file("favicon", branding_assets.FAVICON_EXTS) is not None,
        has_login_bg=branding_assets.find_file("login-bg", branding_assets.ALL_EXTS) is not None,
        has_logo=logo_file is not None,
        logo_updated_at=logo_updated_at,
        allowed_iframe_origins=iframe_origins,
        has_hero_bg_morning=branding_assets.find_file("hero-bg-morning", branding_assets.ALL_EXTS)
        is not None,
        has_hero_bg_day=branding_assets.find_file("hero-bg-day", branding_assets.ALL_EXTS)
        is not None,
        has_hero_bg_evening=branding_assets.find_file("hero-bg-evening", branding_assets.ALL_EXTS)
        is not None,
    )


@router.put("/admin/branding/settings", summary="Сохранить настройки оформления")
async def save_settings(
    body: BrandingSettings, editor: EditorDep, redis: RedisDep
) -> BrandingSettings:
    branding_assets.save_settings(body)
    await _audit(redis, str(editor.id), "settings")
    logger.info("branding.settings_saved")
    return body


# ── Logo ─────────────────────────────────────────────────────────────────────


@router.get("/branding/logo", summary="Получить логотип портала")
@router.head("/branding/logo", include_in_schema=False)
async def get_logo(request: Request) -> Response:
    return _serve_asset(
        request,
        "logo",
        branding_assets.ALL_EXTS,
        default_mime="image/png",
        cache_control=_CACHE_IMMUTABLE,
        not_found="No custom logo set",
    )


@router.post("/admin/branding/logo", summary="Загрузить логотип портала")
async def upload_logo(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="logo",
        exts=branding_assets.ALL_EXTS,
        mime_map=branding_assets.MIME_TO_EXT,
        label="logo",
        target="logo",
    )


@router.delete("/admin/branding/logo", summary="Сбросить логотип к умолчанию")
async def reset_logo(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="logo",
        exts=branding_assets.ALL_EXTS,
        target="logo",
        detail="Logo reset to default",
        log_key="branding.logo_reset",
    )


# ── Favicon ───────────────────────────────────────────────────────────────────


@router.get("/branding/favicon", summary="Получить favicon портала")
@router.head("/branding/favicon", include_in_schema=False)
async def get_favicon(request: Request) -> Response:
    return _serve_asset(
        request,
        "favicon",
        branding_assets.FAVICON_EXTS,
        default_mime="image/x-icon",
        cache_control=_CACHE_SHORT,
        not_found="No custom favicon set",
    )


@router.post("/admin/branding/favicon", summary="Загрузить favicon портала")
async def upload_favicon(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="favicon",
        exts=branding_assets.FAVICON_EXTS,
        mime_map=branding_assets.FAVICON_MIME,
        label="favicon",
        target="favicon",
    )


@router.delete("/admin/branding/favicon", summary="Сбросить favicon к умолчанию")
async def reset_favicon(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="favicon",
        exts=branding_assets.FAVICON_EXTS,
        target="favicon",
        detail="Favicon reset to default",
        log_key="branding.favicon_reset",
    )


# ── Login background ──────────────────────────────────────────────────────────


@router.get("/branding/login-bg", summary="Получить фон страницы входа")
@router.head("/branding/login-bg", include_in_schema=False)
async def get_login_bg(request: Request) -> Response:
    return _serve_asset(
        request,
        "login-bg",
        branding_assets.ALL_EXTS,
        default_mime="image/jpeg",
        cache_control=_CACHE_SHORT,
        not_found="No custom login background set",
    )


@router.post("/admin/branding/login-bg", summary="Загрузить фон страницы входа")
async def upload_login_bg(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="login-bg",
        exts=branding_assets.ALL_EXTS,
        mime_map=branding_assets.MIME_TO_EXT,
        label="login-bg",
        target="login_bg",
    )


@router.delete("/admin/branding/login-bg", summary="Сбросить фон страницы входа")
async def reset_login_bg(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="login-bg",
        exts=branding_assets.ALL_EXTS,
        target="login_bg",
        detail="Login background reset to default",
        log_key="branding.login_bg_reset",
    )


# ── Hero background (morning / day / evening) ─────────────────────────────────
# Механизм идентичен login-bg: по три хендлера (GET/POST/DELETE) на каждый слот.
# Время слотов настраивается в BrandingSettings.hero_*_hour, frontend выбирает
# активный слот по часу и подставляет соответствующее фото.


@router.get("/branding/hero-bg-morning", summary="Фон Hero (утро)")
@router.head("/branding/hero-bg-morning", include_in_schema=False)
async def get_hero_bg_morning(request: Request) -> Response:
    return _serve_asset(
        request,
        "hero-bg-morning",
        branding_assets.ALL_EXTS,
        default_mime="image/jpeg",
        cache_control=_CACHE_SHORT,
        not_found="No hero morning background set",
    )


@router.post("/admin/branding/hero-bg-morning", summary="Загрузить фон Hero (утро)")
async def upload_hero_bg_morning(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="hero-bg-morning",
        exts=branding_assets.ALL_EXTS,
        mime_map=branding_assets.MIME_TO_EXT,
        label="hero-bg-morning",
        target="hero_bg_morning",
    )


@router.delete("/admin/branding/hero-bg-morning", summary="Сбросить фон Hero (утро)")
async def reset_hero_bg_morning(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="hero-bg-morning",
        exts=branding_assets.ALL_EXTS,
        target="hero_bg_morning",
        detail="Hero morning background reset to default",
        log_key="branding.hero_bg_morning_reset",
    )


@router.get("/branding/hero-bg-day", summary="Фон Hero (день)")
@router.head("/branding/hero-bg-day", include_in_schema=False)
async def get_hero_bg_day(request: Request) -> Response:
    return _serve_asset(
        request,
        "hero-bg-day",
        branding_assets.ALL_EXTS,
        default_mime="image/jpeg",
        cache_control=_CACHE_SHORT,
        not_found="No hero day background set",
    )


@router.post("/admin/branding/hero-bg-day", summary="Загрузить фон Hero (день)")
async def upload_hero_bg_day(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="hero-bg-day",
        exts=branding_assets.ALL_EXTS,
        mime_map=branding_assets.MIME_TO_EXT,
        label="hero-bg-day",
        target="hero_bg_day",
    )


@router.delete("/admin/branding/hero-bg-day", summary="Сбросить фон Hero (день)")
async def reset_hero_bg_day(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="hero-bg-day",
        exts=branding_assets.ALL_EXTS,
        target="hero_bg_day",
        detail="Hero day background reset to default",
        log_key="branding.hero_bg_day_reset",
    )


@router.get("/branding/hero-bg-evening", summary="Фон Hero (вечер)")
@router.head("/branding/hero-bg-evening", include_in_schema=False)
async def get_hero_bg_evening(request: Request) -> Response:
    return _serve_asset(
        request,
        "hero-bg-evening",
        branding_assets.ALL_EXTS,
        default_mime="image/jpeg",
        cache_control=_CACHE_SHORT,
        not_found="No hero evening background set",
    )


@router.post("/admin/branding/hero-bg-evening", summary="Загрузить фон Hero (вечер)")
async def upload_hero_bg_evening(file: UploadFile, editor: EditorDep, redis: RedisDep) -> dict:
    return await _upload_asset(
        file,
        redis,
        str(editor.id),
        prefix="hero-bg-evening",
        exts=branding_assets.ALL_EXTS,
        mime_map=branding_assets.MIME_TO_EXT,
        label="hero-bg-evening",
        target="hero_bg_evening",
    )


@router.delete("/admin/branding/hero-bg-evening", summary="Сбросить фон Hero (вечер)")
async def reset_hero_bg_evening(editor: EditorDep, redis: RedisDep) -> dict:
    return await _reset_asset(
        redis,
        str(editor.id),
        prefix="hero-bg-evening",
        exts=branding_assets.ALL_EXTS,
        target="hero_bg_evening",
        detail="Hero evening background reset to default",
        log_key="branding.hero_bg_evening_reset",
    )


# ── Email settings ────────────────────────────────────────────────────────────


@router.get(
    "/admin/email-settings", response_model=EmailSettingsOut, summary="Получить настройки email"
)
async def get_email_settings(_admin: AdminDep) -> EmailSettingsOut:
    """Возвращает текущие настройки SMTP + общего IMAP. Пароли не возвращаются,
    только флаги password_set / imap_password_set."""
    return email_settings.email_settings_to_out(email_settings.load_email_settings())


@router.put(
    "/admin/email-settings", response_model=EmailSettingsOut, summary="Сохранить настройки email"
)
async def save_email_settings(
    body: EmailSettingsIn, admin: AdminDep, redis: RedisDep
) -> EmailSettingsOut:
    """Сохраняет SMTP + общий IMAP в /data/branding/email-settings.json.

    Пароли (SMTP, IMAP) — write-only с keep/clear/update семантикой:
    ``null``/``'***'`` = оставить прежний, ``''`` = очистить, иное = обновить.
    IMAP-пароль хранится Fernet-шифром, SMTP — plaintext (ADR-048).
    """
    existing = email_settings.load_email_settings()
    new_password = existing.password
    if body.password is not None and body.password != email_settings.EMAIL_PASSWORD_MASK:
        new_password = body.password

    # IMAP-пароль: keep/clear/update. По умолчанию — оставляем прежний (plaintext
    # уже расшифрован в модели при load). encode/save зашифрует его на диске.
    new_imap_password = existing.imap_password
    if body.imap_password is not None:
        new_imap_password = body.imap_password

    settings = EmailSettings(
        host=body.host,
        port=body.port,
        from_address=body.from_address,
        username=body.username,
        password=new_password,
        use_tls=body.use_tls,
        use_starttls=body.use_starttls,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        imap_use_ssl=body.imap_use_ssl,
        imap_username=body.imap_username,
        imap_password=new_imap_password,
        imap_folder=body.imap_folder,
    )
    email_settings.save_email_settings(settings)
    await _audit(redis, str(admin.id), "email_settings")
    logger.info(
        "branding.email_settings_saved",
        host=body.host,
        port=body.port,
        imap_host=body.imap_host,
    )
    return email_settings.email_settings_to_out(settings)


@router.post("/admin/email-settings/test", summary="Отправить тестовое письмо")
async def test_email_settings(
    body: EmailTestRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    admin: AdminDep,
    redis: RedisDep,
) -> dict:
    """Отправляет тестовое письмо используя сохранённые SMTP-настройки."""
    settings = email_settings.load_email_settings()
    if not settings.host:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="SMTP host is not configured",
        )
    background_tasks.add_task(
        email_settings.send_test_email, settings=settings, to=body.to, sender_name=user.full_name
    )
    await _audit(redis, str(admin.id), "email_test")
    return {"detail": "Test email queued", "to": body.to}


@router.post("/admin/email-settings/imap/test", summary="Проверить подключение общего IMAP-ящика")
async def test_imap_settings(admin: AdminDep, _redis: RedisDep) -> dict:
    """Проверяет подключение к общему IMAP-ящику (login + select folder).

    Использует сохранённые настройки. Возвращает ``{"ok": bool, "detail": str}``.
    ``detail`` маскируется (aioimaplib может echo'ить LOGIN с паролем — грабля H-9).
    """
    settings = email_settings.load_email_settings()
    ok, detail = await email_settings.test_imap_connection(settings)
    await _audit(_redis, str(admin.id), "email_imap_test")
    return {"ok": ok, "detail": detail}
