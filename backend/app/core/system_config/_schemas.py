from __future__ import annotations

import ipaddress

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DEFAULT_VIDEO_IFRAME_ORIGINS

# Развёртывание стороннего iframe — исполнение чужого кода в браузере
# пользователя: список обязан быть ограниченным.
MAX_VIDEO_IFRAME_ORIGINS = 32


def _normalize_video_iframe_origins(raw: list[str]) -> list[str]:
    """Нормализует и валидирует список origin'ов для iframe/CSP frame-src.

    Каждый элемент приводится к origin ``scheme://host[:port]`` (http/https):
    путь, query и fragment обрезаются (админ может вставить и полный URL),
    хост — к lower. Userinfo, wildcard'ы и пустые элементы отклоняются;
    дубликаты удаляются с сохранением порядка.
    """
    from urllib.parse import urlsplit

    if len(raw) > MAX_VIDEO_IFRAME_ORIGINS:
        raise ValueError(f"No more than {MAX_VIDEO_IFRAME_ORIGINS} origins allowed")
    out: list[str] = []
    for item in raw:
        value = item.strip()
        if not value:
            raise ValueError("Empty origin in video_iframe_origins")
        if len(value) > 255:
            raise ValueError(f"Origin too long: '{value[:50]}…'")
        if "*" in value:
            raise ValueError(f"Wildcards are not allowed in origin: '{value}'")
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"Origin must start with http:// or https://: '{value}'")
        if not parts.hostname:
            raise ValueError(f"Origin must contain a host: '{value}'")
        if parts.username or parts.password:
            raise ValueError(f"Origin must not contain userinfo (user:password@): '{value}'")
        port = f":{parts.port}" if parts.port else ""
        origin = f"{parts.scheme}://{parts.hostname}{port}".lower()
        if origin not in out:
            out.append(origin)
    return out


class OnboardingStep(BaseModel):
    id: str = Field(default="", max_length=64)
    selector: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    is_new: bool = Field(default=False)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v:
            return v
        import re

        if not re.fullmatch(r"[A-Za-z0-9_\-]+", v):
            raise ValueError("id must contain only letters, digits, '-' and '_'")
        return v


class _SystemSettingsBase(BaseModel):
    portal_base_url: str = Field(default="https://portal.company.local")
    # Публичный контур обучения (ADR-050): базовый URL learn-домена. Пусто =
    # публичный контур не введён (nginx не рендерит learn server-блок, CSRF
    # допускает только portal-Origin, письма учёток ссылаются на дефолт).
    learning_base_url: str = Field(default="")
    nextcloud_url: str = Field(default="https://nextcloud.company.local")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_username: str = Field(default="portal-svc")
    nc_files_root: str = Field(default="PortalFiles")
    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    prometheus_metrics_enabled: bool = Field(default=True)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_import_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_trash_retention_days: int = Field(default=30, ge=0, le=3650)
    # Автоочистка уведомлений (cron notifications.cleanup_notifications, 04:25):
    # прочитанные — старше read_retention_days, непрочитанные — старше
    # unread_retention_days (правило 3×, как в почтовом клиенте). 0 = отключить
    # соответствующую ветку независимо.
    notifications_read_retention_days: int = Field(default=30, ge=0, le=3650)
    notifications_unread_retention_days: int = Field(default=90, ge=0, le=3650)
    log_level: str = Field(default="INFO")
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)
    timezone: str = Field(default="Europe/Moscow")
    arq_max_jobs: int = Field(default=10, gt=0, le=200)
    photo_gallery_url: str = Field(default="")
    photo_gallery_mode: str = Field(default="external")
    photo_gallery_new_tab: bool = Field(default=False)
    video_gallery_url: str = Field(default="")
    # Origin'ы, iframe с которых разрешён (CSP frame-src: портал + learn-контур,
    # sanitize-гейт rich-контента и видео-плеер материалов обучения). Управляется
    # в Admin UI → System; default — DEFAULT_VIDEO_IFRAME_ORIGINS.
    video_iframe_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_VIDEO_IFRAME_ORIGINS)
    )
    sse_max_connections_per_user: int = Field(default=10, gt=0, le=100)
    sse_max_connections_global: int = Field(default=2000, gt=0, le=10000)
    phone_extract_regex: str = Field(default="")
    onboarding_enabled: bool = Field(default=True)
    onboarding_reset_trigger: str = Field(default="")

    @field_validator("portal_base_url", "learning_base_url")
    @classmethod
    def _ensure_scheme(cls, v: str) -> str:
        """``portal_base_url``/``learning_base_url`` должны включать scheme
        (http/https) — иначе CSRF Origin-проверка (``urlparse`` даёт пустой
        ``scheme``) ломается и local/learning login возвращает 403. Нормализуем:
        если scheme отсутствует, добавляем ``https://`` (значение без scheme,
        напр. ``portal.local``, приходит из Admin UI или легаси-миграции)."""
        if not v:
            return v
        if "://" not in v:
            return f"https://{v}"
        return v

    onboarding_steps: list[OnboardingStep] | None = Field(default=None)

    @field_validator("phone_extract_regex")
    @classmethod
    def _validate_phone_extract_regex(cls, v: str) -> str:
        if v:
            import re

            try:
                re.compile(v)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
        return v

    @field_validator("allowed_cidr")
    @classmethod
    def _validate_cidr(cls, v: str) -> str:
        for cidr in (c.strip() for c in v.split(",") if c.strip()):
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR '{cidr}': {exc}") from exc
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(v)
        except Exception as exc:
            raise ValueError(
                f"Unknown timezone: '{v}'. Use IANA format, e.g. 'Europe/Moscow', 'UTC'."
            ) from exc
        return v

    @field_validator("video_iframe_origins")
    @classmethod
    def _validate_video_iframe_origins(cls, v: list[str]) -> list[str]:
        return _normalize_video_iframe_origins(v)


class SystemSettings(_SystemSettingsBase):
    nc_service_app_password: str = Field(default="")
    metrics_token: str = Field(default="")


def _validate_https_learning_base(v: str | None) -> str | None:
    """Строгая проверка публичного learn-URL **только на записи** (Admin API).

    Значение попадает в письма восстановления с одноразовым токеном в query:
    явный ``http://`` раскрывает токен первому HTTP-запросу (при этом nginx
    всё равно рендерит только HTTPS-контур с redirect — HTTP не поддерживаемый
    режим, PA-025). Хранимые значения (``SystemSettings``) продолжают
    парситься мягко (``_ensure_scheme``): жёсткий reject при загрузке
    system.json уронил бы ВСЕ настройки на дефолты (_loader.py падает в
    defaults целиком). Fail-closed для легаси-значений делает рендерер
    (render-config.sh: не-HTTPS origin → контур disabled).
    """
    from urllib.parse import urlsplit

    if not v:
        return v
    # Bare host (``learn.mage.ru``) нормализуем к https — как ``_ensure_scheme``
    # в базовой модели; в Patch её нет (она не наследует base), поэтому здесь.
    if "://" not in v:
        v = f"https://{v}"
    parts = urlsplit(v)
    if parts.scheme != "https":
        raise ValueError(
            f"learning_base_url must be an https:// origin, got '{v}'. "
            "HTTP запрещён: в ссылках восстановления передаётся одноразовый токен."
        )
    if not parts.hostname:
        raise ValueError(f"learning_base_url must contain a host: '{v}'")
    if parts.username or parts.password:
        raise ValueError(f"learning_base_url must not contain userinfo (user:password@): '{v}'")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(
            f"learning_base_url must be a bare origin without path/query/fragment: '{v}'"
        )
    return v


class SystemSettingsIn(_SystemSettingsBase):
    nc_service_app_password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    metrics_token: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )

    @field_validator("learning_base_url")
    @classmethod
    def _validate_learning_base_https(cls, v: str) -> str:
        result: str | None = _validate_https_learning_base(v)
        assert result is not None
        return result


class SystemSettingsPatch(BaseModel):
    """Partial-update schema: only provided (non-None) fields are applied."""

    portal_base_url: str | None = None
    learning_base_url: str | None = None
    nextcloud_url: str | None = None
    nc_user_id_field: str | None = None
    nc_service_username: str | None = None
    nc_files_root: str | None = None
    max_upload_size_mb: int | None = Field(default=None, gt=0, le=1024)
    allowed_cidr: str | None = None
    prometheus_metrics_enabled: bool | None = None
    news_attachment_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    kb_media_max_size_mb: int | None = Field(default=None, gt=0, le=512)
    kb_attachment_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    kb_import_max_size_mb: int | None = Field(default=None, gt=0, le=1024)
    kb_trash_retention_days: int | None = Field(default=None, ge=0, le=3650)
    notifications_read_retention_days: int | None = Field(default=None, ge=0, le=3650)
    notifications_unread_retention_days: int | None = Field(default=None, ge=0, le=3650)
    log_level: str | None = None
    log_force_json: bool | None = None
    log_slow_request_ms: int | None = Field(default=None, ge=0)
    timezone: str | None = None
    arq_max_jobs: int | None = Field(default=None, gt=0, le=200)
    photo_gallery_url: str | None = None
    photo_gallery_mode: str | None = None
    photo_gallery_new_tab: bool | None = None
    video_gallery_url: str | None = None
    video_iframe_origins: list[str] | None = None
    sse_max_connections_per_user: int | None = Field(default=None, gt=0, le=100)
    sse_max_connections_global: int | None = Field(default=None, gt=0, le=10000)
    phone_extract_regex: str | None = None
    onboarding_enabled: bool | None = None
    onboarding_steps: list[OnboardingStep] | None = None

    @field_validator("video_iframe_origins")
    @classmethod
    def _validate_video_iframe_origins_patch(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _normalize_video_iframe_origins(v)

    @field_validator("phone_extract_regex")
    @classmethod
    def _validate_phone_extract_regex_patch(cls, v: str | None) -> str | None:
        if v:
            import re

            try:
                re.compile(v)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
        return v

    nc_service_app_password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    metrics_token: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )

    @field_validator("learning_base_url")
    @classmethod
    def _validate_learning_base_https_patch(cls, v: str | None) -> str | None:
        return _validate_https_learning_base(v)

    @field_validator("allowed_cidr")
    @classmethod
    def _validate_cidr(cls, v: str | None) -> str | None:
        if v is None:
            return v
        for cidr in (c.strip() for c in v.split(",") if c.strip()):
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR '{cidr}': {exc}") from exc
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(v)
        except Exception as exc:
            raise ValueError(
                f"Unknown timezone: '{v}'. Use IANA format, e.g. 'Europe/Moscow', 'UTC'."
            ) from exc
        return v


class SystemSettingsOut(BaseModel):
    portal_base_url: str
    learning_base_url: str
    nextcloud_url: str
    nc_user_id_field: str
    nc_service_app_password_set: bool
    max_upload_size_mb: int
    allowed_cidr: str
    prometheus_metrics_enabled: bool
    news_attachment_max_size_mb: int
    kb_media_max_size_mb: int
    kb_attachment_max_size_mb: int
    log_level: str
    timezone: str
    log_force_json: bool | None
    log_slow_request_ms: int
    arq_max_jobs: int
    photo_gallery_url: str
    photo_gallery_mode: str
    photo_gallery_new_tab: bool
    video_gallery_url: str
    video_iframe_origins: list[str]
    nc_service_username: str
    nc_files_root: str
    kb_import_max_size_mb: int
    kb_trash_retention_days: int
    notifications_read_retention_days: int
    notifications_unread_retention_days: int
    metrics_token_set: bool
    phone_extract_regex: str
    onboarding_enabled: bool
    onboarding_reset_trigger: str
    onboarding_steps: list[OnboardingStep] | None = None


class GalleryLinksOut(BaseModel):
    photo_gallery_url: str | None
    photo_gallery_mode: str
    photo_gallery_new_tab: bool
    video_gallery_url: str | None
