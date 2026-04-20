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
    portal_base_url: str = Field(default="https://portal.company.local")

    database_url: str
    redis_url: str

    keycloak_url: str
    keycloak_realm: str = Field(default="company")
    keycloak_client_id: str = Field(default="portal")
    keycloak_client_secret: str

    nextcloud_url: str = Field(default="https://nextcloud.company.local")
    nc_user_id_field: str = Field(default="preferred_username")
    nc_service_app_password: str = Field(default="")

    max_upload_size_mb: int = Field(default=100, gt=0, le=1024)
    allowed_cidr: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")

    smtp_host: str = Field(default="postfix")
    smtp_port: int = Field(default=25)
    smtp_from: str = Field(default="portal@company.local")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
