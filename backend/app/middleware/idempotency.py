from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

logger = get_logger(__name__)

_IDEMPOTENT_PATHS = frozenset(
    {
        "/api/v1/news",
        "/api/v1/kb/articles",
        "/api/v1/files/folders",
        "/api/v1/notifications/send",
    }
)

_CACHE_TTL = 86400
# Lease-модель (audit-review 2026-08-22, P1 «lock истекает через 30 секунд»):
# TTL обязан покрывать максимальную длительность защищаемого запроса, иначе
# конкурент с тем же ключом выполнит операцию повторно. 120с ≈ ceiling
# медленных POST (news с обложкой, kb-статья с вложениями); короче —
# ретраи клиентов таймаутятся раньше и не создают гонку.
_LOCK_TTL = 120
_KEY_PREFIX = "idempotency:"
_LOCK_PREFIX = "idempotency_lock:"
# v3: ключ теперь включает fingerprint запроса (method+path+body) — записи
# старого формата инвалидируются разово после деплоя (одна miss-гонка ≤ TTL).
_CACHE_VERSION = 3

# audit [PA-020]: middleware буферизует тело запроса до auth/ACL/rate-limit.
# Жёсткий потолок буферизации: превышение → идемпотентность для запроса
# отключается, запрос проходит сквозь middleware как есть (без 413 — деградация
# до «нет дедупликации» лучше отказа операции). Покрываемые пути — маленькие
# JSON; 10 МБ на порядки выше любого легитимного тела и на 1-2 порядка ниже
# лимита upload'ов (nginx client_max_body_size = max_upload_size_mb).
_MAX_BUFFERED_BODY = 10 * 1024 * 1024


async def _release_lock_atomic(redis: object, lock_key: str, lock_value: str) -> None:
    """Атомарный compare-and-delete через WATCH (audit-review P1).

    Наивный GET→DELETE неатомарен: между ними лок мог истечь и перехвачен
    другим воркером — delete снял бы ЧУЖОЙ лок. WATCH-транзакция проверяет
    значение и удаляет атомарно. (Lua-скрипт тот же эффект даёт на реальном
    Redis, но fakeredis исполняет Lua только с lupa — WATCH работает везде.)
    """
    pipe = redis.pipeline(transaction=True)  # type: ignore[attr-defined]
    try:
        await pipe.watch(lock_key)
        current = await pipe.get(lock_key)
        if current == lock_value:
            pipe.multi()
            pipe.delete(lock_key)
            await pipe.execute()
        else:
            await pipe.unwatch()
    finally:
        await pipe.reset()


def _request_fingerprint(method: str, path: str, body: bytes) -> str:
    """Fingerprint операции: method + path + тело.

    Один Idempotency-Key, переиспользованный на другой операции (другой роут
    или другое тело), НЕ должен получать чужой закэшированный ответ — это
    отдельная операция, а не ретрай (audit-review 2026-08-22, P1).
    """
    h = hashlib.sha256()
    h.update(method.encode("ascii", "ignore"))
    h.update(b"\x00")
    h.update(path.encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update(body)
    return h.hexdigest()[:24]


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


def _get_session_id_from_cookie(scope: Scope) -> str:
    headers = dict(scope.get("headers", []))
    cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("portal_session="):
            return str(part[len("portal_session=") :])
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
        is_target = idem_key and request.method == "POST" and (path in _IDEMPOTENT_PATHS)

        if not is_target:
            await self.app(scope, receive, send)
            return

        # audit [PA-020]: multipart (upload-роуты) не буферизуем никогда —
        # у files upload есть собственный user-scoped idempotency-cache после
        # auth/rate-limit (app/api/files/upload.py), общий fingerprint ему не
        # нужен, а буферизация multipart в RAM до auth — memory amplification.
        if self._content_type(scope).startswith("multipart/"):
            await self.app(scope, receive, send)
            return

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            await self.app(scope, receive, send)
            return

        session_id = _get_session_id_from_cookie(scope)

        # Вычитываем тело запроса (нужен для fingerprint) и подменяем receive
        # на повторяющий — приложение прочитает его как в первый раз. Тело
        # выше _MAX_BUFFERED_BODY не буферизуем: request проходит сквозь
        # middleware без дедупликации (receive добирает остаток из канала).
        buffered, overflow = await self._read_body_capped(receive, _MAX_BUFFERED_BODY)
        if overflow:
            logger.warning(
                "idempotency.body_too_large_skipped",
                path=path,
                buffered_bytes=len(buffered),
                limit=_MAX_BUFFERED_BODY,
            )
            await self.app(scope, self._resuming_receive(buffered, receive), send)
            return

        body = buffered

        fingerprint = _request_fingerprint(request.method, path, body)
        cache_key = f"{_KEY_PREFIX}{session_id}:{idem_key}:{fingerprint}"
        lock_key = f"{_LOCK_PREFIX}{session_id}:{idem_key}:{fingerprint}"

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
                content={
                    "detail": "A request with this Idempotency-Key is already being processed"
                },
            )
            await response(scope, receive, send)
            return

        try:
            body_chunks: list[bytes] = []
            status_code_holder: list[int] = [200]
            headers_holder: list[list[tuple[bytes, bytes]]] = [[]]

            async def capture_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    status_code_holder[0] = message["status"]
                    headers_holder[0] = list(message.get("headers", []))
                elif message["type"] == "http.response.body":
                    body_chunks.append(message.get("body", b""))
                await send(message)

            replaying_receive = self._replaying_receive(body)
            await self.app(scope, replaying_receive, capture_send)

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
            with contextlib.suppress(Exception):
                await _release_lock_atomic(redis, lock_key, lock_value)

    @staticmethod
    def _content_type(scope: Scope) -> str:
        headers = dict(scope.get("headers", []))
        raw: str = headers.get(b"content-type", b"").decode("latin-1", errors="ignore")
        return raw.strip().lower()

    @staticmethod
    async def _read_body_capped(receive: Receive, limit: int) -> tuple[bytes, bool]:
        """Читать тело запроса не более ``limit`` байт.

        Возвращает ``(буфер, overflow)``. При ``overflow=True`` прочитано
        ``> limit`` байт (не более одного чанка сверх лимита), а канал receive
        ещё содержит остаток — вызывающий обязан докормить приложение через
        ``_resuming_receive``.
        """
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunk = message.get("body", b"")
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                return b"".join(chunks), True
            if not message.get("more_body", False):
                break
        return b"".join(chunks), False

    @staticmethod
    def _resuming_receive(buffered: bytes, receive: Receive) -> Receive:
        """Receive, сначала однократно возвращающий уже прочитанный буфер,
        затем проксирующий живой канал с остатком тела."""
        state = {"buf": buffered}

        async def _receive() -> Message:
            if state["buf"]:
                buf = state["buf"]
                state["buf"] = b""
                return {"type": "http.request", "body": buf, "more_body": True}
            return await receive()

        return _receive

    @staticmethod
    def _replaying_receive(body: bytes) -> Receive:
        """Receive, однократно возвращающий сохранённое тело, дальше — пустые чанки."""
        state = {"sent": False}

        async def _receive() -> Message:
            if not state["sent"]:
                state["sent"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        return _receive

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
