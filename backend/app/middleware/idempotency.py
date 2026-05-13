from __future__ import annotations

import base64
import contextlib
import json
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, Response
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
_CACHE_VERSION = 2

_CACHED_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-disposition",
        "content-encoding",
        "content-language",
        "cache-control",
        "etag",
        "location",
        "x-resource-id",
    }
)

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def _get_session_id_from_cookie(scope) -> str:
    headers = dict(scope.get("headers", []))
    cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("portal_session="):
            return part[len("portal_session="):]
    return "anonymous"


def _filter_headers(raw_headers: list[tuple[bytes, bytes]]) -> list[tuple[str, str]]:
    """Keep a whitelist of response headers safe to replay."""
    out: list[tuple[str, str]] = []
    for name_b, value_b in raw_headers:
        name = name_b.decode("latin-1").lower()
        if name in _HOP_BY_HOP:
            continue
        if name not in _CACHED_HEADERS:
            continue
        out.append((name, value_b.decode("latin-1")))
    return out


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
            replay = self._build_replay_response(cached)
            if replay is not None:
                await replay(scope, receive, send)
                return

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
            headers_holder: list[list[tuple[bytes, bytes]]] = [[]]

            async def capture_send(message) -> None:
                if message["type"] == "http.response.start":
                    status_code_holder[0] = message["status"]
                    headers_holder[0] = list(message.get("headers", []))
                elif message["type"] == "http.response.body":
                    body_chunks.append(message.get("body", b""))
                await send(message)

            await self.app(scope, receive, capture_send)

            status_code = status_code_holder[0]
            if status_code in (200, 201):
                body = b"".join(body_chunks)
                resource_id = self._extract_resource_id(body)
                entry = {
                    "v": _CACHE_VERSION,
                    "status_code": status_code,
                    "headers": _filter_headers(headers_holder[0]),
                    "body_b64": base64.b64encode(body).decode("ascii"),
                    "resource_id": resource_id,
                }
                with contextlib.suppress(Exception):
                    await redis.setex(cache_key, _CACHE_TTL, json.dumps(entry))
        finally:
            current = await redis.get(lock_key)
            if current and current == lock_value:
                await redis.delete(lock_key)

    @staticmethod
    def _extract_resource_id(body: bytes) -> str:
        try:
            parsed = json.loads(body)
        except Exception:
            return ""
        if isinstance(parsed, dict):
            value = parsed.get("id", "")
            return str(value) if value is not None else ""
        return ""

    @staticmethod
    def _build_replay_response(cached: str | bytes) -> Response | None:
        try:
            entry = json.loads(cached)
        except Exception:
            return None
        if not isinstance(entry, dict):
            return None

        if entry.get("v") == _CACHE_VERSION and "body_b64" in entry:
            try:
                body = base64.b64decode(entry["body_b64"])
            except Exception:
                return None
            status_code = int(entry.get("status_code", 200))
            headers: dict[str, str] = {}
            for item in entry.get("headers", []) or []:
                if (
                    isinstance(item, (list, tuple))
                    and len(item) == 2
                    and isinstance(item[0], str)
                    and isinstance(item[1], str)
                ):
                    headers[item[0]] = item[1]
            headers["X-Idempotency-Replayed"] = "true"
            resource_id = str(entry.get("resource_id") or "")
            if resource_id and "x-resource-id" not in headers:
                headers["X-Resource-Id"] = resource_id
            response = Response(content=body, status_code=status_code)
            for name, value in headers.items():
                response.headers[name] = value
            return response

        resource_id = str(entry.get("resource_id", "") or "")
        status_code = int(entry.get("status_code", 200))
        return JSONResponse(
            content={"id": resource_id} if resource_id else {},
            status_code=status_code,
            headers={
                "X-Idempotency-Replayed": "true",
                "X-Resource-Id": resource_id,
            },
        )
