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

    nextcloud_url: str = Field(default="")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_app_password: str = Field(default="")

    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    news_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    kb_media_max_size_mb: int = Field(default=20, gt=0, le=512)
    kb_attachment_max_size_mb: int = Field(default=50, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")

    local_auth_enabled: bool = Field(default=True)
    admin_email: str | None = Field(default=None)
    admin_password: str | None = Field(default=None)
    admin_password_reset_on_start: bool = Field(
        default=False,
        description=(
            "Опасно: при True пароль bootstrap-админа перезаписывается значением из "
            "ADMIN_PASSWORD при каждом запуске. По умолчанию False — пароль пишется "
            "только при создании пользователя."
        ),
    )

    peertube_url: str = Field(default="")
    peertube_public_url: str = Field(default="")
    peertube_client_id: str = Field(default="")
    peertube_client_secret: str = Field(default="")
    peertube_svc_username: str = Field(default="")
    peertube_svc_password: str = Field(default="")
    peertube_channel_id: str = Field(default="")

    sentry_dsn: str = Field(default="")
    prometheus_metrics_enabled: bool = Field(default=True)
    db_echo: bool = Field(default=False)

    arq_max_jobs: int = Field(default=10)

    tz: str = Field(default="Europe/Moscow")

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
    return Settings()
