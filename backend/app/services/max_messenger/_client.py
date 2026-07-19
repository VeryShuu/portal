"""Singleton ``httpx.AsyncClient`` for MAX Bot API + request helpers.

Patterns borrowed from :mod:`app.services.keycloak.http_client` (lifespan
singleton) and :mod:`app.services.nextcloud.webdav._client` (named timeouts,
reused clients instead of per-request ``async with``).

Authorization: MAX uses a bare token in the ``Authorization`` header
(``Authorization: <bot_token>``, **no** ``Bearer`` prefix — see
https://dev.max.ru/docs-api). The token is passed per-call (not baked into
the shared client) so the singleton serves all tenants/settings-reloads.
"""

from __future__ import annotations

import ssl
from typing import Any, Literal

import httpx

from app.core.logging import get_logger
from app.worker.tasks.email_utils import ErrorClass

logger = get_logger(__name__)

# platform-api.max.ru deprecated c 19.07.2026 (см. dev.max.ru/docs-api —
# migration notice). Используем сразу новый домен platform-api2.max.ru.
MAX_BASE_URL = "https://platform-api2.max.ru"
MAX_TEXT_LIMIT = 4096  # MAX ограничивает text сообщения ~4 KB.

# Connect timeout короче read: MAX API отвечает быстро на /messages, но
# TLS-handshake может задерживаться на корпоративном прокси.
_MAX_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_LIMITS = httpx.Limits(max_keepalive_connections=5, max_connections=10)

# httpx по умолчанию использует ``certifi.where()`` как CA-bundle (свой
# собственный, не системный). В certifi **нет** Russian Trusted Root CA
# (Минцифры), поэтому исходящие запросы к российским сервисам (MAX Bot API,
# Госуслуги) падают с CERTIFICATE_VERIFY_FAILED, даже после добавления
# сертификата в систему через ``update-ca-certificates`` (см. backend/Dockerfile).
# Решение: передаём httpx системный SSLContext — он подхватывает и системный
# bundle (/etc/ssl/certs/ca-certificates.crt), и сертификаты из
# /usr/local/share/ca-certificates/.
_MAX_SSL_CONTEXT = ssl.create_default_context()

# Module-level singleton (lifespan-managed through init/close).
_MAX_HTTP_CLIENT: httpx.AsyncClient | None = None


def _client_kwargs() -> dict:
    """Общие kwargs для создания httpx.AsyncClient (singleton и lazy-init)."""
    return {
        "timeout": _MAX_TIMEOUT,
        "limits": _MAX_LIMITS,
        "verify": _MAX_SSL_CONTEXT,
        "headers": {"User-Agent": "portal-helpdesk/1.0 (+max-bot-api)"},
    }


def _get_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared MAX httpx client.

    Lazy-init is the safety net for code paths that don't run inside the
    FastAPI lifespan (tests, ad-hoc scripts): a fresh client is created on
    demand and closed by ``close_max_http_client``.
    """
    global _MAX_HTTP_CLIENT
    if _MAX_HTTP_CLIENT is None or _MAX_HTTP_CLIENT.is_closed:
        _MAX_HTTP_CLIENT = httpx.AsyncClient(**_client_kwargs())
    return _MAX_HTTP_CLIENT


async def init_max_http_client() -> None:
    """Eagerly initialise the shared client (FastAPI lifespan startup)."""
    global _MAX_HTTP_CLIENT
    if _MAX_HTTP_CLIENT is None or _MAX_HTTP_CLIENT.is_closed:
        _MAX_HTTP_CLIENT = httpx.AsyncClient(**_client_kwargs())


async def close_max_http_client() -> None:
    """Close the shared client (FastAPI lifespan shutdown)."""
    global _MAX_HTTP_CLIENT
    if _MAX_HTTP_CLIENT is not None and not _MAX_HTTP_CLIENT.is_closed:
        await _MAX_HTTP_CLIENT.aclose()
    _MAX_HTTP_CLIENT = None


class MaxApiError(Exception):
    """Raised when MAX Bot API returns a non-2xx response or transport fails.

    Carries the HTTP status code (when available) so the outbox worker can
    classify it via :func:`classify_http_error`.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _auth_headers(bot_token: str) -> dict[str, str]:
    """MAX uses ``Authorization: <token>`` without the ``Bearer`` prefix."""
    return {
        "Authorization": bot_token,
        "Content-Type": "application/json",
    }


async def send_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
    format_: Literal["markdown", "html"] = "markdown",
    notify: bool = True,
) -> dict[str, Any]:
    """Send a message to a MAX chat via ``POST /messages``.

    Endpoint: ``POST /messages?chat_id=<chat_id>`` with JSON body
    ``{text, format, attachments, notify}``. Returns the parsed JSON response
    (contains ``message`` object with ``body``, ``recipient`` etc.).

    Raises :class:`MaxApiError` on non-2xx status or transport failure.
    """
    body = {
        "text": text,
        "format": format_,
        "attachments": attachments or [],
        "notify": notify,
    }
    client = _get_client()
    try:
        resp = await client.post(
            f"{MAX_BASE_URL}/messages",
            params={"chat_id": chat_id},
            json=body,
            headers=_auth_headers(bot_token),
        )
    except httpx.HTTPError as exc:
        # Transport-level: timeout, connection refused, DNS, TLS — обёртка,
        # чтобы воркер классифицировал как transient и ретраил.
        raise MaxApiError(f"MAX API transport error: {type(exc).__name__}") from exc

    if resp.status_code >= 400:
        # MAX возвращает JSON-ошибку {code, message}. Логируем без токена.
        try:
            err = resp.json()
            msg = str(err.get("message") or err.get("code") or resp.text)
        except Exception:
            msg = resp.text or f"HTTP {resp.status_code}"
        raise MaxApiError(
            f"MAX API returned HTTP {resp.status_code}: {msg[:300]}",
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except Exception as exc:
        # Ответ не JSON — на успех это нетипично, но не роняем отправку:
        # outbox всё равно mark_sent, чтобы не зацикливать ретраи на
        # малозначимом парсинге. Лог оставляем для разбора.
        logger.warning(
            "max_messenger.send_message.unexpected_response",
            chat_id=chat_id,
            status=resp.status_code,
            snippet=resp.text[:200],
        )
        return {"_raw": resp.text, "_parse_error": str(exc)}
    return data if isinstance(data, dict) else {"_raw": data}


async def get_me(bot_token: str) -> dict[str, Any]:
    """Call ``GET /me`` to verify the bot token. Used by ``POST /max-bot/test``.

    Returns the bot profile JSON (``{user_id, name, username, ...}``).
    Raises :class:`MaxApiError` on non-2xx.
    """
    client = _get_client()
    try:
        resp = await client.get(
            f"{MAX_BASE_URL}/me",
            headers=_auth_headers(bot_token),
        )
    except httpx.HTTPError as exc:
        raise MaxApiError(f"MAX API transport error: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        try:
            err = resp.json()
            msg = str(err.get("message") or err.get("code") or resp.text)
        except Exception:
            msg = resp.text or f"HTTP {resp.status_code}"
        raise MaxApiError(
            f"MAX API returned HTTP {resp.status_code}: {msg[:300]}",
            status_code=resp.status_code,
        )
    me = resp.json()
    return me if isinstance(me, dict) else {"_raw": me}


def classify_http_error(exc: BaseException) -> ErrorClass:
    """Classify a MAX-API exception for outbox retry/DLQ decisions.

    Semantics mirrors :func:`app.worker.tasks.email_utils.classify_smtp_error`:
    * transient  — сетевые/5xx/429: worth retrying with backoff;
    * permanent  — auth/4xx (except 429): fix the config, no retry;
    * unknown    — everything else: retry cautiously.

    A MAX :class:`MaxApiError` carries ``status_code``; bare httpx exceptions
    (Timeout/NetworkError) are inherently transient.
    """
    status: int | None = getattr(exc, "status_code", None)
    if status is not None:
        if status == 429 or 500 <= status < 600:
            return "transient"
        if 400 <= status < 600:  # 4xx (except 429 caught above)
            return "permanent"
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError):
        return "transient"
    if isinstance(exc, httpx.HTTPError):
        # Не классифицированный httpx — лучше ретраить осторожно.
        return "unknown"
    return "unknown"
