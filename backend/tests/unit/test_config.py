import pytest
from pydantic import ValidationError


def make_env(**overrides) -> dict:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://portal:secret@localhost:5432/portal",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "exactly_thirty_two_characters_ok!",
        "ENVIRONMENT": "development",
    }
    base.update(overrides)
    return base


def test_valid_config(monkeypatch):
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.environment == "development"
    assert s.is_production is False


def test_production_flag(monkeypatch):
    env = make_env(ENVIRONMENT="production")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.is_production is True


def test_secret_key_too_short_raises(monkeypatch):
    env = make_env(SECRET_KEY="tooshort")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("secret_key",) for e in errors)


def test_invalid_database_url_driver(monkeypatch):
    env = make_env(DATABASE_URL="postgresql://portal:secret@localhost:5432/portal")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    errors = exc_info.value.errors()
    assert any("database_url" in str(e["loc"]) for e in errors)


def test_defaults(monkeypatch):
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.local_auth_enabled is True
    assert s.db_pool_size == 20


def test_legacy_runtime_fields_removed(monkeypatch):
    """Sanity check: fields moved to SystemSettings (ADR-037) must NOT be on
    bootstrap Settings any more — prevents accidental re-introduction.
    """
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    for removed in (
        "keycloak_url",
        "keycloak_realm",
        "keycloak_client_id",
        "keycloak_client_secret",
        "portal_base_url",
        "max_upload_size_mb",
        "news_attachment_max_size_mb",
        "kb_media_max_size_mb",
        "kb_attachment_max_size_mb",
        "kb_import_max_size_mb",
        "allowed_cidr",
        "prometheus_metrics_enabled",
        "metrics_token",
        "sentry_dsn",
        "log_level",
        "log_force_json",
        "log_slow_request_ms",
        "arq_max_jobs",
        "nc_files_root",
        "nc_service_username",
    ):
        assert not hasattr(s, removed), f"Settings.{removed} must be moved to SystemSettings"
