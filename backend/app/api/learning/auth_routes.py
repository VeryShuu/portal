"""Аутентификация внешних обучаемых: ``/api/v1/auth/learning/*``.

Passwordless (миграция 113): вход = email → одноразовый код письмом →
verify → сессия. Все эндпоинты публичного контура — жёсткие rate-limits
(IP + email-хэш), origin-only CSRF-пути — в ``app/middleware/csrf.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi_limiter.depends import RateLimiter

from app.api.deps import LearningDbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.core.cookies import request_is_secure
from app.core.limiter import email_identifier, probe_bypass_rate_limit
from app.schemas.learning import (
    LearningLoginRequest,
    LearningVerifyRequest,
)
from app.services.audit import push_audit_event
from app.services.learning import accounts_service as svc
from app.services.learning.sessions import COOKIE_NAME, delete_session

router = APIRouter(
    prefix="/auth/learning",
    tags=["auth"],
    # Как остальные learning-роуты: выключенный модуль → 404 на весь контур,
    # включая вход (§8 ТЗ, паттерн require_helpdesk_module).
    dependencies=[Depends(_module_gate)],
)

# Публичная пара эндпоинтов входа: IP 5/15м + email-хэш 10/15м (как local-login).
# Перебор самого кода дополнительно закрыт attempts-счётчиком кода (5 вводов).
_LOGIN_LIMITS = [
    Depends(probe_bypass_rate_limit(times=5, minutes=15)),
    Depends(RateLimiter(times=10, minutes=15, identifier=email_identifier)),
]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/login",
    summary="Запрос кода входа (шаг 1)",
    dependencies=_LOGIN_LIMITS,
)
async def learning_request_code(
    body: LearningLoginRequest,
    request: Request,
    db: LearningDbDep,
) -> dict[str, Any]:
    # Отправка только существующей активной учётке; ответ одинаков всегда —
    # анти-enumeration (§10.4 ТЗ). Письмо уходит через outbox (~10 с).
    await svc.request_login_code(db, email=body.email)
    return {"ok": True}


@router.post(
    "/verify",
    summary="Вход по коду из письма (шаг 2)",
    dependencies=_LOGIN_LIMITS,
)
async def learning_verify(
    body: LearningVerifyRequest,
    request: Request,
    redis: RedisDep,
    db: LearningDbDep,
) -> JSONResponse:
    outcome = await svc.verify_login_code(db, email=body.email, code=body.code)
    if outcome is None:
        # Единый ответ: нет учётки / нет активного кода / неверный код / истёк /
        # исчерпаны попытки — анти-enumeration и никаких уточнений переборщику.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    old_session_id = request.cookies.get(COOKIE_NAME)
    session_id = await svc.create_login_session(redis, outcome, old_session_id)
    await push_audit_event(
        redis,
        event_type="learning.login",
        resource_type="learning_account",
        resource_id=str(outcome.account.id),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    resp = JSONResponse({"ok": True})
    svc.set_session_cookie(resp, session_id, secure=request_is_secure(request))
    return resp


@router.post(
    "/logout",
    summary="Выход обучаемого",
)
async def learning_logout(request: Request, response: Response, redis: RedisDep) -> dict[str, Any]:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        await delete_session(redis, session_id)
    svc.clear_session_cookie(response)
    return {"ok": True}
