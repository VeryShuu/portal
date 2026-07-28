import pytest
from pydantic import ValidationError


def make_env(**overrides) -> dict:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://portal:secret@localhost:5432/portal",
        "REDIS_URL": "redis://localhost:6379/0",
        # 33 символа — проходит Field.min_length=32; достаточно для dev/test.
        # Для production-тестов передавайте SECRET_KEY явно (≥48 символов).
        "SECRET_KEY": "exactly_thirty_two_characters_ok!",
        "ENVIRONMENT": "development",
    }
    base.update(overrides)
    return base


# Валидный SECRET_KEY для production-тестов: 96 hex = результат `openssl rand -hex 48`.
# Не входит в block-list, длина ≥ 48.
_VALID_PROD_SECRET = "a" * 96


def test_valid_config(monkeypatch):
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.environment == "development"
    assert s.is_production is False


def test_production_flag(monkeypatch):
    env = make_env(ENVIRONMENT="production", SECRET_KEY=_VALID_PROD_SECRET)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.is_production is True


# ── audit [C1]: production-валидаторы секретов ─────────────────────────────


def test_production_rejects_default_secret_key(monkeypatch):
    """В production отвергается публично известный SECRET_KEY из .env.example."""
    env = make_env(
        ENVIRONMENT="production",
        SECRET_KEY="change_me_32_chars_minimum_secret_key_here",
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "publicly-known default" in str(exc_info.value)


def test_production_rejects_short_secret_key(monkeypatch):
    """В production SECRET_KEY должен быть ≥48 символов (32-символьный отклонён)."""
    env = make_env(
        ENVIRONMENT="production",
        SECRET_KEY="exactly_thirty_two_characters_ok!",  # 33 символа
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "at least 48 characters" in str(exc_info.value)


def test_production_rejects_default_admin_password(monkeypatch):
    """В production ADMIN_PASSWORD='change_me_on_first_login' отклоняется."""
    env = make_env(
        ENVIRONMENT="production",
        SECRET_KEY=_VALID_PROD_SECRET,
        ADMIN_PASSWORD="change_me_on_first_login",
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "change_me_on_first_login" in str(exc_info.value)


def test_production_accepts_empty_admin_password(monkeypatch):
    """Пустой ADMIN_PASSWORD допустим в production (bootstrap пропускается)."""
    env = make_env(
        ENVIRONMENT="production",
        SECRET_KEY=_VALID_PROD_SECRET,
        ADMIN_EMAIL="",
        ADMIN_PASSWORD="",
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.is_production is True
    assert s.admin_password in (None, "")


def test_dev_accepts_short_secret_key(monkeypatch):
    """Регресс: dev/test остаются на min_length=32 (CI-фикстуры, локальная разработка).

    Валидатор production-секретов НЕ должен срабатывать вне production.
    """
    env = make_env(ENVIRONMENT="development")  # SECRET_KEY=33 символа из make_env
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.environment == "development"
    assert s.is_production is False


def test_dev_accepts_default_admin_password(monkeypatch):
    """dev/staging не валидирует ADMIN_PASSWORD (обратная совместимость)."""
    env = make_env(
        ENVIRONMENT="staging",
        SECRET_KEY="exactly_thirty_two_characters_ok!",
        ADMIN_PASSWORD="change_me_on_first_login",
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from app.core.config import Settings

    s = Settings()
    assert s.environment == "staging"
    assert s.admin_password == "change_me_on_first_login"


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


def test_photos_thumb_defaults(monkeypatch):
    """PS-5: process-level photo tuning lands on bootstrap Settings with the
    same defaults the env-flags used to provide.
    """
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for var in ("PHOTOS_GENERATE_AVIF", "PHOTOS_AVIF_MIN_SIZE", "PHOTOS_THUMB_CONCURRENCY"):
        monkeypatch.delenv(var, raising=False)

    from app.core.config import Settings

    s = Settings()
    assert s.photos_generate_avif is True
    assert s.photos_avif_min_size == 1000
    assert s.photos_thumb_concurrency == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", False),
        ("false", False),
        ("False", False),
        ("", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("anything", True),
    ],
)
def test_photos_generate_avif_parsing_matches_legacy(monkeypatch, value, expected):
    """Boolean parsing is 1:1 with the previous ``os.environ`` logic in
    photos_storage: only "0"/"false"/"False"/"" disable AVIF.
    """
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PHOTOS_GENERATE_AVIF", value)

    from app.core.config import Settings

    assert Settings().photos_generate_avif is expected


def test_photos_thumb_env_override(monkeypatch):
    env = make_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PHOTOS_AVIF_MIN_SIZE", "600")
    monkeypatch.setenv("PHOTOS_THUMB_CONCURRENCY", "4")

    from app.core.config import Settings

    s = Settings()
    assert s.photos_avif_min_size == 600
    assert s.photos_thumb_concurrency == 4


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
        "log_level",
        "log_force_json",
        "log_slow_request_ms",
        "arq_max_jobs",
        "nc_files_root",
        "nc_service_username",
    ):
        assert not hasattr(s, removed), f"Settings.{removed} must be moved to SystemSettings"
