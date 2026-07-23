from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from app.api.health import router

    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_always_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_no_auth_required(self, client):
        response = client.get("/health")
        assert response.status_code == 200


class TestReadyEndpoint:
    def test_ready_ok_when_db_and_redis_healthy(self, client):
        from app.core.modules_config import AllModuleSettings

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
            patch("app.api.modules.load_modules", return_value=AllModuleSettings()),
        ):
            response = client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["redis"] == "ok"

    def test_ready_503_when_db_fails(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(side_effect=Exception("DB connection refused"))

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
        ):
            response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["checks"]["postgres"] == "error"
        assert body["checks"]["redis"] == "ok"

    def test_ready_503_when_redis_fails(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection refused"))

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
        ):
            response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["redis"] == "error"

    def test_ready_503_when_both_fail(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(side_effect=Exception("DB down"))

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
        ):
            response = client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["checks"]["postgres"] == "error"
        assert body["checks"]["redis"] == "error"

    def test_ready_response_has_checks_dict(self, client):
        from app.core.modules_config import AllModuleSettings

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
            patch("app.api.modules.load_modules", return_value=AllModuleSettings()),
        ):
            response = client.get("/ready")

        body = response.json()
        assert "checks" in body
        assert "postgres" in body["checks"]
        assert "redis" in body["checks"]

    def test_ready_stays_200_when_keycloak_down(self, client):
        """Keycloak/SMTP/Collabora down — non-fatal, /ready остаётся 200.

        Логика: портал готов, если DB+Redis живы. Интеграции degraded,
        но local-auth fallback и контент работают.
        """
        from app.core.modules_config import AllModuleSettings

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
            patch("app.api.modules.load_modules", return_value=AllModuleSettings()),
            patch(
                "app.worker.tasks.integration_health._probe_keycloak",
                AsyncMock(return_value=False),
            ),
            patch(
                "app.worker.tasks.integration_health._probe_smtp",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.worker.tasks.integration_health._probe_collabora",
                AsyncMock(return_value=None),
            ),
        ):
            response = client.get("/ready")

        # /ready остаётся 200 — Keycloak down не делает портал "не готов"
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["redis"] == "ok"
        assert body["checks"]["keycloak"] == "error"
        assert body["checks"]["smtp"] == "ok"

    def test_ready_includes_integration_status(self, client):
        """Body содержит per-component status интеграций."""
        from app.core.modules_config import AllModuleSettings

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
            patch("app.api.modules.load_modules", return_value=AllModuleSettings()),
            patch(
                "app.worker.tasks.integration_health._probe_keycloak",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.worker.tasks.integration_health._probe_smtp",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.worker.tasks.integration_health._probe_collabora",
                AsyncMock(return_value=None),
            ),
        ):
            response = client.get("/ready")

        body = response.json()["checks"]
        assert body["keycloak"] == "unconfigured"
        assert body["smtp"] == "unconfigured"
