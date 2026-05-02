from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_IDEMPOTENT_PATHS = frozenset(
    {
        "/api/v1/news",
        "/api/v1/kb/articles",
        "/api/v1/files/folders",
    }
)

_CACHE_TTL = 86400
_KEY_PREFIX = "idempotency:"


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        idem_key = request.headers.get("Idempotency-Key")
        is_target = idem_key and request.method == "POST" and request.url.path in _IDEMPOTENT_PATHS

        if is_target:
            redis = getattr(request.app.state, "redis", None)
            if redis is not None:
                cache_key = f"{_KEY_PREFIX}{idem_key}"
                cached = await redis.get(cache_key)
                if cached is not None:
                    try:
                        entry = json.loads(cached)
                        response = JSONResponse(
                            content=entry["body"],
                            status_code=entry["status_code"],
                            headers={"X-Idempotency-Replayed": "true"},
                        )
                        await response(scope, receive, send)
                        return
                    except Exception:
                        pass

        body_chunks: list[bytes] = []
        status_code_holder: list[int] = [200]
        headers_holder: list[list] = [[]]

        async def capture_send(message) -> None:
            if message["type"] == "http.response.start":
                status_code_holder[0] = message["status"]
                headers_holder[0] = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, capture_send)

        if is_target and status_code_holder[0] in (200, 201):
            redis = getattr(request.app.state, "redis", None)
            if redis is not None:
                body = b"".join(body_chunks)
                try:
                    parsed = json.loads(body)
                    cache_key = f"{_KEY_PREFIX}{idem_key}"
                    await redis.setex(
                        cache_key,
                        _CACHE_TTL,
                        json.dumps({"body": parsed, "status_code": status_code_holder[0]}),
                    )
                except Exception:
                    pass
