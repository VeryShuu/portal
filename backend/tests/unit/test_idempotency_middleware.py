"""Contract tests for IdempotencyMiddleware.

Verifies that a replayed response is byte-for-byte equal to the original
response (status + whitelisted headers + body).
"""
from __future__ import annotations

import json

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.middleware.idempotency import IdempotencyMiddleware


pytestmark = pytest.mark.asyncio


def _build_client(handler):
    try:
        import fakeredis.aioredis as fakeredis_aio
    except ImportError:  # pragma: no cover
        pytest.skip("fakeredis not installed")

    routes = [Route("/api/v1/news", handler, methods=["POST", "GET"])]
    app = Starlette(routes=routes, middleware=[Middleware(IdempotencyMiddleware)])
    app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestIdempotencyReplayContract:
    async def test_replays_status_headers_and_body_byte_for_byte(self):
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            payload = {"id": "res-1", "n": call_count["n"], "name": "Привет"}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return Response(
                content=body,
                status_code=201,
                media_type="application/json",
                headers={
                    "Location": "/api/v1/news/res-1",
                    "ETag": '"abc123"',
                    "X-Resource-Id": "res-1",
                    "Cache-Control": "no-store",
                },
            )

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "key-1"}
            first = await client.post("/api/v1/news", headers=headers)
            second = await client.post("/api/v1/news", headers=headers)

        assert first.status_code == 201
        assert second.status_code == first.status_code
        assert second.content == first.content
        assert call_count["n"] == 1

        for name in ("content-type", "location", "etag", "x-resource-id", "cache-control"):
            assert second.headers.get(name) == first.headers.get(name), (
                f"header {name!r} mismatch"
            )

        assert second.headers.get("x-idempotency-replayed") == "true"
        assert "x-idempotency-replayed" not in first.headers

    async def test_replay_does_not_invoke_handler(self):
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            return JSONResponse({"id": f"r-{call_count['n']}"}, status_code=201)

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "key-2"}
            first = await client.post("/api/v1/news", headers=headers)
            second = await client.post("/api/v1/news", headers=headers)
            third = await client.post("/api/v1/news", headers=headers)

        assert call_count["n"] == 1
        assert first.json() == {"id": "r-1"}
        assert second.json() == {"id": "r-1"}
        assert third.json() == {"id": "r-1"}

    async def test_different_keys_invoke_handler_separately(self):
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            return JSONResponse({"id": f"r-{call_count['n']}"}, status_code=201)

        async with _build_client(handler) as client:
            a = await client.post("/api/v1/news", headers={"Idempotency-Key": "key-A"})
            b = await client.post("/api/v1/news", headers={"Idempotency-Key": "key-B"})

        assert call_count["n"] == 2
        assert a.json() != b.json()

    async def test_non_post_bypasses_middleware(self):
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            return JSONResponse({"ok": True})

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "key-3"}
            await client.get("/api/v1/news", headers=headers)
            await client.get("/api/v1/news", headers=headers)
        assert call_count["n"] == 2

    async def test_non_2xx_response_is_not_cached(self):
        call_count = {"n": 0}

        async def handler(request: Request) -> Response:
            call_count["n"] += 1
            return JSONResponse({"detail": "boom"}, status_code=500)

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "key-err"}
            await client.post("/api/v1/news", headers=headers)
            await client.post("/api/v1/news", headers=headers)
        assert call_count["n"] == 2

    async def test_replay_preserves_non_id_body_shape(self):
        async def handler(request: Request) -> Response:
            payload = {"items": [1, 2, 3], "meta": {"total": 3}}
            return JSONResponse(payload, status_code=200)

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "key-shape"}
            first = await client.post("/api/v1/news", headers=headers)
            second = await client.post("/api/v1/news", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json() == first.json() == {"items": [1, 2, 3], "meta": {"total": 3}}
        assert second.content == first.content
