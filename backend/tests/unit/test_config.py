import pytest
from pydantic import ValidationError


def make_env(**overrides) -> dict:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://portal:secret@localhost:5432/portal",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "exactly_thirty_two_characters_ok!",
        "KEYCLOAK_URL": "https://auth.company.local",
        "KEYCLOAK_CLIENT_SECRET": "kc_secret",
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
    assert s.max_upload_size_mb == 100
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


def test_max_upload_size_bytes(monkeypatch):
    env = make_env(MAX_UPLOAD_SIZE_MB="50")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.max_upload_size_mb == 50
    assert s.max_upload_size_bytes == 50 * 1024 * 1024


def test_max_upload_size_zero_raises(monkeypatch):
    env = make_env(MAX_UPLOAD_SIZE_MB="0")
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings()


def test_defaults(monkeypatch):
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.keycloak_realm == "company"
    assert s.keycloak_client_id == "portal"
    assert s.arq_max_jobs == 10
    assert s.prometheus_metrics_enabled is True
    assert s.sentry_dsn == ""
