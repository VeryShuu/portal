from __future__ import annotations

import json
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_IDEMPOTENT_PATHS = frozenset(
    {
        "/api/v1/news",
        "/api/v1/kb/articles",
        "/api/v1/files/folders",
        "/api/v1/notifications/send",
    }
)

_IDEMPOTENT_PREFIXES = (
    "/api/v1/files/folders/",
)

_CACHE_TTL = 86400
_LOCK_TTL = 30
_KEY_PREFIX = "idempotency:"
_LOCK_PREFIX = "idempotency_lock:"


def _get_session_id_from_cookie(scope) -> str:
    headers = dict(scope.get("headers", []))
    cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("portal_session="):
            return part[len("portal_session="):]
    return "anonymous"


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        idem_key = request.headers.get("Idempotency-Key")
        path = request.url.path
        is_target = (
            idem_key
            and request.method == "POST"
            and (
                path in _IDEMPOTENT_PATHS
                or any(path.startswith(p) for p in _IDEMPOTENT_PREFIXES)
            )
        )

        if not is_target:
            await self.app(scope, receive, send)
            return

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            await self.app(scope, receive, send)
            return

        session_id = _get_session_id_from_cookie(scope)
        cache_key = f"{_KEY_PREFIX}{session_id}:{idem_key}"
        lock_key = f"{_LOCK_PREFIX}{session_id}:{idem_key}"

        cached = await redis.get(cache_key)
        if cached is not None:
            try:
                entry = json.loads(cached)
                resource_id = entry.get("resource_id", "")
                status_code = entry.get("status_code", 200)
                response = JSONResponse(
                    content={"id": resource_id} if resource_id else {},
                    status_code=status_code,
                    headers={
                        "X-Idempotency-Replayed": "true",
                        "X-Resource-Id": resource_id or "",
                    },
                )
                await response(scope, receive, send)
                return
            except Exception:
                pass

        lock_value = secrets.token_hex(8)
        acquired = await redis.set(lock_key, lock_value, ex=_LOCK_TTL, nx=True)
        if not acquired:
            response = JSONResponse(
                status_code=409,
                content={"detail": "A request with this Idempotency-Key is already being processed"},  # noqa: E501
            )
            await response(scope, receive, send)
            return

        try:
            body_chunks: list[bytes] = []
            status_code_holder: list[int] = [200]

            async def capture_send(message) -> None:
                if message["type"] == "http.response.start":
                    status_code_holder[0] = message["status"]
                elif message["type"] == "http.response.body":
                    body_chunks.append(message.get("body", b""))
                await send(message)

            await self.app(scope, receive, capture_send)

            if status_code_holder[0] in (200, 201):
                body = b"".join(body_chunks)
                try:
                    parsed = json.loads(body)
                    resource_id = str(parsed.get("id", "")) if isinstance(parsed, dict) else ""
                    await redis.setex(
                        cache_key,
                        _CACHE_TTL,
                        json.dumps({"resource_id": resource_id, "status_code": status_code_holder[0]}),  # noqa: E501
                    )
                except Exception:
                    pass
        finally:
            current = await redis.get(lock_key)
            if current and current == lock_value:
                await redis.delete(lock_key)
