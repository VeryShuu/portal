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
            assert second.headers.get(name) == first.headers.get(name), f"header {name!r} mismatch"

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


class TestRequestFingerprint:
    """audit-review 2026-08-22, P1: ключ кэша обязан включать fingerprint операции.

    Один Idempotency-Key на ДРУГОЙ операции (иной роут или иное тело) — это не
    ретрай, а отдельный запрос: он не должен получать чужой закэшированный ответ.
    """

    async def test_same_key_different_path_executes_both(self):
        import fakeredis.aioredis as fakeredis_aio
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        from app.middleware.idempotency import IdempotencyMiddleware

        calls: list[str] = []

        async def news(request: Request) -> JSONResponse:
            calls.append("news")
            return JSONResponse({"op": "news"})

        async def folders(request: Request) -> JSONResponse:
            calls.append("folders")
            return JSONResponse({"op": "folders"})

        app = Starlette(
            routes=[
                Route("/api/v1/news", news, methods=["POST"]),
                Route("/api/v1/files/folders", folders, methods=["POST"]),
            ],
            middleware=[Middleware(IdempotencyMiddleware)],
        )
        app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Idempotency-Key": "reused-key"}
            r1 = await client.post("/api/v1/news", headers=headers, json={"title": "A"})
            r2 = await client.post("/api/v1/files/folders", headers=headers, json={"title": "A"})

        assert r1.json() == {"op": "news"}
        assert r2.json() == {"op": "folders"}, "другой роут — отдельная операция, не replay"
        assert calls == ["news", "folders"]

    async def test_same_key_different_body_executes_both(self):
        async def handler(request: Request) -> JSONResponse:
            body = await request.json()
            return JSONResponse({"created": body["title"]})

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "same-key"}
            r1 = await client.post("/api/v1/news", headers=headers, json={"title": "first"})
            r2 = await client.post("/api/v1/news", headers=headers, json={"title": "second"})

        assert r1.json() == {"created": "first"}
        assert r2.json() == {"created": "second"}, "другое тело — отдельная операция, не replay"

    async def test_retry_with_identical_request_replays(self):
        calls = {"n": 0}

        async def handler(request: Request) -> JSONResponse:
            calls["n"] += 1
            return JSONResponse({"id": "res-1"})

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "retry-key"}
            r1 = await client.post("/api/v1/news", headers=headers, json={"title": "same"})
            r2 = await client.post("/api/v1/news", headers=headers, json={"title": "same"})

        assert r1.json() == r2.json()
        assert calls["n"] == 1, "идентичный ретрай обязан получить replay"


# ── audit [PA-020]: middleware не буферизует multipart/oversize тела ─────────


class TestNoMultipartBuffering:
    async def test_multipart_is_not_deduplicated(self):
        """multipart-запрос с Idempotency-Key проходит сквозь middleware без
        fingerprint-буферизации: два идентичных запроса = два исполнения
        (у upload-роута собственный user-scoped idempotency после auth)."""
        calls = {"n": 0}

        async def handler(request: Request) -> JSONResponse:
            calls["n"] += 1
            form = await request.form()
            uploads = [f for f in form.getlist("files") if not isinstance(f, str)]
            return JSONResponse({"files": [f.filename for f in uploads]})

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "upload-key"}
            files = [("files", ("a.txt", b"content-a", "text/plain"))]
            r1 = await client.post("/api/v1/news", headers=headers, files=files)
            r2 = await client.post("/api/v1/news", headers=headers, files=files)

        assert r1.json() == {"files": ["a.txt"]}
        assert r2.json() == {"files": ["a.txt"]}
        assert calls["n"] == 2, "multipart не должен попадать в дедупликацию middleware"

    async def test_upload_prefix_not_captured_at_all(self):
        """Префикс /api/v1/files/folders/ больше не в _IDEMPOTENT_PATHS:
        upload-роут защищён собственным user-scoped кэшем (PA-020)."""
        calls = {"n": 0}

        async def handler(request: Request) -> JSONResponse:
            calls["n"] += 1
            return JSONResponse({"id": "res-1"})

        routes = [Route("/api/v1/files/folders/abc/upload", handler, methods=["POST"])]
        import fakeredis.aioredis as fakeredis_aio

        app = Starlette(routes=routes, middleware=[Middleware(IdempotencyMiddleware)])
        app.state.redis = fakeredis_aio.FakeRedis(decode_responses=True)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Idempotency-Key": "upload-key"}
            await client.post("/api/v1/files/folders/abc/upload", headers=headers)
            await client.post("/api/v1/files/folders/abc/upload", headers=headers)
        assert calls["n"] == 2


class TestOversizeBodyPassThrough:
    async def test_oversize_body_skips_dedup_and_delivers_full_body(self, monkeypatch):
        """Тело выше потолка не буферизуется: запрос проходит сквозь middleware
        как есть (без 409/replay), приложение получает тело ЦЕЛИКОМ — уже
        прочитанная часть докармливается через resuming receive."""
        import app.middleware.idempotency as idem_module

        monkeypatch.setattr(idem_module, "_MAX_BUFFERED_BODY", 64)
        calls = {"n": 0}

        async def handler(request: Request) -> JSONResponse:
            calls["n"] += 1
            raw = await request.body()
            return JSONResponse({"size": len(raw)})

        async with _build_client(handler) as client:
            headers = {"Idempotency-Key": "big-key"}
            payload = b"x" * 1000
            r1 = await client.post(
                "/api/v1/news",
                headers=headers,
                content=payload,
            )
            r2 = await client.post(
                "/api/v1/news",
                headers=headers,
                content=payload,
            )

        assert r1.json() == {"size": 1000}, "хвост тела не потерян после переполнения буфера"
        assert r2.json() == {"size": 1000}
        assert calls["n"] == 2, "oversize-запрос не кэшируется и не реплеится"
