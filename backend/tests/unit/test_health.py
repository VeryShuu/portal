from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
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
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock())

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("app.api.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.api.health.get_redis", return_value=mock_redis),
        ):
            response = client.get("/ready")

        body = response.json()
        assert "checks" in body
        assert "postgres" in body["checks"]
        assert "redis" in body["checks"]
