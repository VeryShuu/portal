from __future__ import annotations

import ipaddress

from pydantic import BaseModel, Field, field_validator


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
    log_level: str = Field(default="INFO")
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)
    timezone: str = Field(default="Europe/Moscow")
    arq_max_jobs: int = Field(default=10, gt=0, le=200)
    photo_gallery_url: str = Field(default="")
    photo_gallery_mode: str = Field(default="external")
    photo_gallery_new_tab: bool = Field(default=False)
    video_gallery_url: str = Field(default="")
    sse_max_connections_per_user: int = Field(default=10, gt=0, le=100)
    sse_max_connections_global: int = Field(default=2000, gt=0, le=10000)
    phone_extract_regex: str = Field(default="")
    onboarding_enabled: bool = Field(default=True)
    onboarding_reset_trigger: str = Field(default="")

    @field_validator("portal_base_url")
    @classmethod
    def _ensure_scheme(cls, v: str) -> str:
        """``portal_base_url`` должен включать scheme (http/https) — иначе CSRF
        Origin-проверка (``urlparse`` даёт пустой ``scheme``) ломается и local
        login возвращает 403. Нормализуем: если scheme отсутствует, добавляем
        ``https://`` (значение без scheme, напр. ``portal.local``, приходит из
        Admin UI или легаси-миграции)."""
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


class SystemSettings(_SystemSettingsBase):
    nc_service_app_password: str = Field(default="")
    metrics_token: str = Field(default="")


class SystemSettingsIn(_SystemSettingsBase):
    nc_service_app_password: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )
    metrics_token: str | None = Field(
        default=None,
        description="Pass null or '***' to keep existing; new value to update; '' to clear",
    )


class SystemSettingsPatch(BaseModel):
    """Partial-update schema: only provided (non-None) fields are applied."""

    portal_base_url: str | None = None
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
    log_level: str | None = None
    log_force_json: bool | None = None
    log_slow_request_ms: int | None = Field(default=None, ge=0)
    timezone: str | None = None
    arq_max_jobs: int | None = Field(default=None, gt=0, le=200)
    photo_gallery_url: str | None = None
    photo_gallery_mode: str | None = None
    photo_gallery_new_tab: bool | None = None
    video_gallery_url: str | None = None
    sse_max_connections_per_user: int | None = Field(default=None, gt=0, le=100)
    sse_max_connections_global: int | None = Field(default=None, gt=0, le=10000)
    phone_extract_regex: str | None = None
    onboarding_enabled: bool | None = None
    onboarding_steps: list[OnboardingStep] | None = None

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
    nc_service_username: str
    nc_files_root: str
    kb_import_max_size_mb: int
    kb_trash_retention_days: int
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
