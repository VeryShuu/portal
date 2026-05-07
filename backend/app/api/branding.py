"""Branding endpoints: logo, favicon, login background, portal settings, email settings."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, CurrentUser, RedisDep
from app.core.logging import get_logger
from app.core.system_config import load_system_settings
from app.core.uploads import stream_upload_to_path
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(tags=["branding"])

_BRANDING_DIR = Path("/data/branding")
_SETTINGS_FILE = _BRANDING_DIR / "settings.json"
_MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB

_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_EXT_TO_MIME: dict[str, str] = {v: k for k, v in _MIME_TO_EXT.items()}
_ALL_EXTS = list(_MIME_TO_EXT.values())

_FAVICON_MIME: dict[str, str] = {
    **_MIME_TO_EXT,
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
_FAVICON_EXTS = list(_FAVICON_MIME.values())


class BrandingSettings(BaseModel):
    portal_name: str = "Корпоративный портал"
    portal_tagline: str = ""
    accent_color: str = "#d8262c"
    welcome_subtitle: str = ""
    banner_enabled: bool = False
    banner_text: str = ""
    banner_type: Literal["info", "warning", "error", "success"] = "info"
    banner_expires_at: str | None = None


class BrandingSettingsOut(BrandingSettings):
    has_favicon: bool = False
    has_login_bg: bool = False
    has_logo: bool = False
    logo_updated_at: str | None = None
    allowed_iframe_origins: list[str] = []


_DEFAULT_SETTINGS = BrandingSettings()

_EMAIL_SETTINGS_FILE = _BRANDING_DIR / "email-settings.json"
_EMAIL_PASSWORD_MASK = "***"


class EmailSettings(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="", description="Masked as '***' in GET response if set")
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)


class EmailSettingsIn(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing password; pass '' to clear; pass new value to update",
    )
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)


class EmailSettingsOut(BaseModel):
    host: str
    port: int
    from_address: str
    username: str
    password_set: bool
    use_tls: bool
    use_starttls: bool


class EmailTestRequest(BaseModel):
    to: str = Field(description="Email address to send test message to")


def _load_email_settings() -> EmailSettings:
    if _EMAIL_SETTINGS_FILE.exists():
        try:
            return EmailSettings.model_validate_json(_EMAIL_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            logger.exception("email_settings.load_failed")
    return EmailSettings()


def _save_email_settings(s: EmailSettings) -> None:
    import os as _os

    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    _EMAIL_SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    # email-settings.json содержит SMTP-пароль.
    with contextlib.suppress(OSError):
        _os.chmod(_EMAIL_SETTINGS_FILE, 0o600)


def _email_settings_to_out(s: EmailSettings) -> EmailSettingsOut:
    return EmailSettingsOut(
        host=s.host,
        port=s.port,
        from_address=s.from_address,
        username=s.username,
        password_set=bool(s.password),
        use_tls=s.use_tls,
        use_starttls=s.use_starttls,
    )


def _load_settings() -> BrandingSettings:
    if _SETTINGS_FILE.exists():
        try:
            return BrandingSettings.model_validate_json(_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return _DEFAULT_SETTINGS.model_copy()


def _save_settings(s: BrandingSettings) -> None:
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(s.model_dump_json(indent=2), encoding="utf-8")


def _find_file(prefix: str, exts: list[str]) -> Path | None:
    for ext in exts:
        p = _BRANDING_DIR / f"{prefix}{ext}"
        if p.exists():
            return p
    return None


def _delete_files(prefix: str, exts: list[str]) -> None:
    for ext in exts:
        (_BRANDING_DIR / f"{prefix}{ext}").unlink(missing_ok=True)


async def _upload_image(
    file: UploadFile,
    prefix: str,
    exts: list[str],
    mime_map: dict[str, str],
    label: str,
) -> str:
    # Pre-check declared MIME — even though stream_upload_to_path re-validates
    # via libmagic, this short-circuits obviously wrong uploads before any I/O.
    if file.content_type not in mime_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported format for {label}",
        )
    ext = mime_map[file.content_type]
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    dest = _BRANDING_DIR / f"{prefix}{ext}"
    size, _detected = await stream_upload_to_path(
        file,
        dest,
        max_size=_MAX_IMAGE_SIZE,
        allowed_mimes=set(mime_map.keys()),
    )
    # Drop any sibling extensions belonging to the previous upload.
    for other_ext in exts:
        if other_ext != ext:
            (_BRANDING_DIR / f"{prefix}{other_ext}").unlink(missing_ok=True)
    logger.info("branding.file_uploaded", prefix=prefix, ext=ext, size=size)
    return f"/api/v1/branding/{prefix.lstrip('/')}"


# ── Settings ─────────────────────────────────────────────────────────────────


@router.get("/branding/settings", summary="Настройки оформления портала")
async def get_settings() -> BrandingSettingsOut:
    s = _load_settings()
    sys = load_system_settings()
    iframe_origins: list[str] = []
    if sys.video_gallery_url:
        iframe_origins.append(sys.video_gallery_url)
    logo_file = _find_file("logo", _ALL_EXTS)
    logo_updated_at = str(int(logo_file.stat().st_mtime)) if logo_file else None
    return BrandingSettingsOut(
        **s.model_dump(),
        has_favicon=_find_file("favicon", _FAVICON_EXTS) is not None,
        has_login_bg=_find_file("login-bg", _ALL_EXTS) is not None,
        has_logo=logo_file is not None,
        logo_updated_at=logo_updated_at,
        allowed_iframe_origins=iframe_origins,
    )


@router.put("/admin/branding/settings", summary="Сохранить настройки оформления")
async def save_settings(
    body: BrandingSettings, admin: AdminDep, redis: RedisDep
) -> BrandingSettings:
    _save_settings(body)
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "settings"},
    )
    logger.info("branding.settings_saved")
    return body


# ── Logo ─────────────────────────────────────────────────────────────────────


@router.api_route("/branding/logo", methods=["GET", "HEAD"], summary="Получить логотип портала")
async def get_logo(request: Request) -> Response:
    logo = _find_file("logo", _ALL_EXTS)
    if not logo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom logo set")
    mime = _EXT_TO_MIME.get(logo.suffix, "image/png")
    if request.method == "HEAD":
        return Response(headers={"Content-Type": mime, "Cache-Control": "public, max-age=31536000, immutable"})
    return FileResponse(logo, media_type=mime, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.post("/admin/branding/logo", summary="Загрузить логотип портала")
async def upload_logo(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict:
    url = await _upload_image(file, "logo", _ALL_EXTS, _MIME_TO_EXT, "logo")
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "logo"},
    )
    return {"url": url}


@router.delete("/admin/branding/logo", summary="Сбросить логотип к умолчанию")
async def reset_logo(admin: AdminDep, redis: RedisDep) -> dict:
    _delete_files("logo", _ALL_EXTS)
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "logo"},
    )
    logger.info("branding.logo_reset")
    return {"detail": "Logo reset to default"}


# ── Favicon ───────────────────────────────────────────────────────────────────


@router.api_route("/branding/favicon", methods=["GET", "HEAD"], summary="Получить favicon портала")
async def get_favicon(request: Request) -> Response:
    fav = _find_file("favicon", _FAVICON_EXTS)
    if not fav:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No custom favicon set")
    mime = _EXT_TO_MIME.get(fav.suffix) or ("image/x-icon" if fav.suffix == ".ico" else "image/png")
    if request.method == "HEAD":
        return Response(headers={"Content-Type": mime, "Cache-Control": "public, max-age=3600"})
    return FileResponse(fav, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})


@router.post("/admin/branding/favicon", summary="Загрузить favicon портала")
async def upload_favicon(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict:
    url = await _upload_image(file, "favicon", _FAVICON_EXTS, _FAVICON_MIME, "favicon")
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "favicon"},
    )
    return {"url": url}


@router.delete("/admin/branding/favicon", summary="Сбросить favicon к умолчанию")
async def reset_favicon(admin: AdminDep, redis: RedisDep) -> dict:
    _delete_files("favicon", _FAVICON_EXTS)
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "favicon"},
    )
    logger.info("branding.favicon_reset")
    return {"detail": "Favicon reset to default"}


# ── Login background ──────────────────────────────────────────────────────────


@router.api_route(
    "/branding/login-bg", methods=["GET", "HEAD"], summary="Получить фон страницы входа"
)
async def get_login_bg(request: Request) -> Response:
    bg = _find_file("login-bg", _ALL_EXTS)
    if not bg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No custom login background set"
        )
    mime = _EXT_TO_MIME.get(bg.suffix, "image/jpeg")
    if request.method == "HEAD":
        return Response(headers={"Content-Type": mime, "Cache-Control": "public, max-age=3600"})
    return FileResponse(bg, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})


@router.post("/admin/branding/login-bg", summary="Загрузить фон страницы входа")
async def upload_login_bg(file: UploadFile, admin: AdminDep, redis: RedisDep) -> dict:
    url = await _upload_image(file, "login-bg", _ALL_EXTS, _MIME_TO_EXT, "login-bg")
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "login_bg"},
    )
    return {"url": url}


@router.delete("/admin/branding/login-bg", summary="Сбросить фон страницы входа")
async def reset_login_bg(admin: AdminDep, redis: RedisDep) -> dict:
    _delete_files("login-bg", _ALL_EXTS)
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "login_bg"},
    )
    logger.info("branding.login_bg_reset")
    return {"detail": "Login background reset to default"}


# ── Email settings ────────────────────────────────────────────────────────────


@router.get(
    "/admin/email-settings", response_model=EmailSettingsOut, summary="Получить настройки email"
)
async def get_email_settings(_admin: AdminDep) -> EmailSettingsOut:
    """Возвращает текущие настройки SMTP. Пароль не возвращается, только флаг password_set."""
    return _email_settings_to_out(_load_email_settings())


@router.put(
    "/admin/email-settings", response_model=EmailSettingsOut, summary="Сохранить настройки email"
)
async def save_email_settings(
    body: EmailSettingsIn, admin: AdminDep, redis: RedisDep
) -> EmailSettingsOut:
    """Сохраняет настройки SMTP в /data/branding/email-settings.json.
    Переопределяет значения из .env — они больше не используются для отправки.
    Если password передан как null или '***' — существующий пароль не меняется.
    """
    existing = _load_email_settings()
    new_password = existing.password
    if body.password is not None and body.password != _EMAIL_PASSWORD_MASK:
        new_password = body.password

    settings = EmailSettings(
        host=body.host,
        port=body.port,
        from_address=body.from_address,
        username=body.username,
        password=new_password,
        use_tls=body.use_tls,
        use_starttls=body.use_starttls,
    )
    _save_email_settings(settings)
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "email_settings"},
    )
    logger.info("branding.email_settings_saved", host=body.host, port=body.port)
    return _email_settings_to_out(settings)


@router.post("/admin/email-settings/test", summary="Отправить тестовое письмо")
async def test_email_settings(
    body: EmailTestRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    admin: AdminDep,
    redis: RedisDep,
) -> dict:
    """Отправляет тестовое письмо используя сохранённые SMTP-настройки."""
    settings = _load_email_settings()
    if not settings.host:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="SMTP host is not configured",
        )
    background_tasks.add_task(
        _send_test_email, settings=settings, to=body.to, sender_name=user.full_name
    )
    await push_audit_event(
        redis,
        event_type="branding.updated",
        user_id=str(admin.id),
        resource_type="branding",
        metadata={"target": "email_test"},
    )
    return {"detail": "Test email queued", "to": body.to}


async def _send_test_email(settings: EmailSettings, to: str, sender_name: str) -> None:
    try:
        import html as _html
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        import aiosmtplib

        sender_esc = _html.escape(sender_name or "", quote=True)
        host_esc = _html.escape(settings.host or "", quote=True)
        subject = "Тестовое письмо от Корпоративного портала"
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Тест</title></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <table width="600" align="center" style="background:#fff;border-radius:8px;margin:32px auto;padding:32px">
    <tr><td>
      <h2 style="color:#143a66;margin:0 0 16px">Корпоративный портал</h2>
      <p style="font-size:16px;color:#333">Это тестовое письмо отправлено администратором <strong>{sender_esc}</strong>.</p>
      <p style="font-size:14px;color:#666">Если вы получили это письмо — настройки SMTP работают корректно.</p>
      <p style="margin-top:24px;font-size:12px;color:#999">Сервер: {host_esc}:{settings.port}</p>
    </td></tr>
  </table>
</body>
</html>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.from_address or "portal@company.local"
        msg["To"] = to
        msg.attach(
            MIMEText(
                "Тестовое письмо от Корпоративного портала. SMTP работает корректно.",
                "plain",
                "utf-8",
            )
        )
        msg.attach(MIMEText(html, "html", "utf-8"))

        smtp_kwargs: dict = {"hostname": settings.host, "port": settings.port}
        if settings.use_tls:
            smtp_kwargs["use_tls"] = True
        if settings.use_starttls:
            smtp_kwargs["start_tls"] = True
        if settings.username and settings.password:
            smtp_kwargs["username"] = settings.username
            smtp_kwargs["password"] = settings.password

        await aiosmtplib.send(msg, **smtp_kwargs)
        logger.info("branding.test_email_sent", to=to)
    except Exception as exc:
        logger.exception(
            "branding.test_email_failed", error=str(exc), error_type=type(exc).__name__, to=to
        )
