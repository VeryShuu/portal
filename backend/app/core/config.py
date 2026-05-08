from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development")
    secret_key: str = Field(min_length=32)
    portal_base_url: str = Field(default="")

    @field_validator("portal_base_url", mode="before")
    @classmethod
    def _validate_portal_base_url(cls, v: object) -> object:
        if not v or v == "":
            return ""
        if isinstance(v, str):
            from urllib.parse import urlparse as _up

            parsed = _up(v)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(
                    "PORTAL_BASE_URL must be a valid http(s) URL or empty string, "
                    f"got: {v!r}"
                )
        return v

    log_level: str = Field(default="INFO")
    log_force_json: bool | None = Field(default=None)
    log_slow_request_ms: int = Field(default=1000, ge=0)

    @field_validator("log_force_json", mode="before")
    @classmethod
    def _parse_log_force_json(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v

    database_url: str
    redis_url: str

    keycloak_url: str = Field(default="")
    keycloak_realm: str = Field(default="company")
    keycloak_client_id: str = Field(default="portal")
    keycloak_client_secret: str = Field(default="")

    nc_service_username: str = Field(default="portal-svc")
    nc_files_root: str = Field(default="PortalFiles")

    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_import_max_size_mb: int = Field(default=50, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")

    local_auth_enabled: bool = Field(default=True)
    admin_email: str | None = Field(default=None)
    admin_password: str | None = Field(default=None)

    @field_validator("admin_password", mode="before")
    @classmethod
    def _strip_admin_password(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    admin_password_reset_on_start: bool = Field(
        default=False,
        description=(
            "Опасно: при True пароль bootstrap-админа перезаписывается значением из "
            "ADMIN_PASSWORD при каждом запуске. По умолчанию False — пароль пишется "
            "только при создании пользователя."
        ),
    )

    screenshot_service_url: str = Field(default="http://screenshot-service:9000")
    screenshot_service_secret: str = Field(default="")

    sentry_dsn: str = Field(default="")
    prometheus_metrics_enabled: bool = Field(default=True)
    metrics_token: str = Field(default="")
    db_echo: bool = Field(default=False)
    db_pool_size: int = Field(default=20, gt=0, le=200)
    db_max_overflow: int = Field(default=30, ge=0, le=200)
    db_pool_recycle: int = Field(default=3600, gt=0)

    arq_max_jobs: int = Field(default=10)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg:// driver")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def news_attachment_max_size_bytes(self) -> int:
        return self.news_attachment_max_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
