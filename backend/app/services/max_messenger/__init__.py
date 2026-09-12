"""MAX (max.ru) Bot API client — async httpx wrapper.

MAX — российский корпоративный мессенджер от VK/Сбер. Bot API base URL:
``https://platform-api2.max.ru`` (домен ``platform-api.max.ru`` deprecated
с 19.07.2026). Авторизация — заголовок ``Authorization: <bot_token>``
(без ``Bearer``).

Документация: https://dev.max.ru/docs-api

Используется из ``app.worker.tasks.messenger_outbox`` (доставка outbox) и из
``app.api.helpdesk.settings`` (``POST /max-bot/test`` через ``get_me``).
Клиент — module-level singleton (lifespan-managed), как в
:mod:`app.services.keycloak.http_client`.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.services.max_messenger._client import (
    MaxApiError,
    classify_http_error,
    close_max_http_client,
    get_me,
    init_max_http_client,
    send_message,
)

logger = get_logger(__name__)

__all__ = [
    "MaxApiError",
    "classify_http_error",
    "close_max_http_client",
    "get_me",
    "init_max_http_client",
    "send_message",
]


# Re-export httpx exceptions for convenience in callers/tests that need to
# simulate transport errors without importing httpx directly.
TransportError = httpx.TransportError
NetworkError = httpx.NetworkError
TimeoutException = httpx.TimeoutException
