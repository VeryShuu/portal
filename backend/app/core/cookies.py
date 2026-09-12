"""Единая политика cookie-флага Secure (ADR-021).

Флаг ``Secure`` определяется фактическим протоколом запроса — заголовком
``X-Forwarded-Proto``, который проставляет nginx (fallback — схема запроса), —
а не ``ENVIRONMENT``: портал по умолчанию поднимается на HTTP без TLS
(ADR-020), и Secure-кука по HTTP молча отбрасывается браузером (логин
возвращает 200, следующий запрос — 401). ENVIRONMENT при этом допускает
обратный перекос: staging/non-production HTTPS получал куки без Secure.

Все точки выдачи cookie (local login, OIDC callback/refresh, XSRF, learner-
сессия обучения) обязаны использовать :func:`request_is_secure`.
"""

from __future__ import annotations

from starlette.requests import Request


def request_is_secure(request: Request) -> bool:
    """Secure-кука уместна, только если запрос пришёл по HTTPS (ADR-021)."""
    proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    return str(proto).lower() == "https"
