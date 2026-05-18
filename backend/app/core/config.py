from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Bootstrap-only environment configuration.

    Holds parameters that must be available BEFORE the filesystem-backed
    runtime config (`/data/settings/system.json`) is reachable: database/Redis
    connection strings, secrets, the bootstrap admin credentials and process-
    level tunables that cannot be hot-reloaded (DB pool sizing).

    Runtime-mutable application settings (URLs, upload limits, allowed CIDR,
    log level/format, Sentry DSN, Prometheus, etc.) live in
    `app.core.system_config.SystemSettings` and are managed via the Admin UI.
    See ADR-037 for the rationale.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Field(default="development")
    secret_key: str = Field(min_length=32)

    database_url: str
    redis_url: str

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

    db_pool_size: int = Field(default=20, gt=0, le=200)
    db_max_overflow: int = Field(default=30, ge=0, le=200)
    db_pool_recycle: int = Field(default=3600, gt=0)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg:// driver")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
