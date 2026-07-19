"""Logout endpoints: ``POST /auth/logout`` и ``GET /auth/logout`` (SLO)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import CurrentUser, RedisDep
from app.core.security import SESSION_COOKIE_NAME
from app.services.audit import push_audit_event
from app.services.session import delete_session, get_session_from_request

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/logout", summary="Logout — destroy session + SLO")
async def logout(
    user: CurrentUser,
    redis: RedisDep,
    request: Request,
) -> RedirectResponse:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = await get_session_from_request(request, redis)
    auth_source = (session_data or {}).get("auth_source", "keycloak")

    if session_id:
        await delete_session(redis, session_id)

    await push_audit_event(
        redis,
        event_type="auth.logout",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        metadata={"source": auth_source},
    )

    # NB: deliberately do NOT call kc_service.get_logout_url() —
    # we keep the Keycloak SSO session alive so domain users get a transparent
    # re-login on next portal visit. Acceptable for intranet (см. ADR).
    if auth_source == "local":
        redirect = RedirectResponse(
            url="/auth/local?logged_out=1", status_code=status.HTTP_302_FOUND
        )
    else:
        redirect = RedirectResponse(
            url="/auth/error?reason=logged_out", status_code=status.HTTP_302_FOUND
        )

    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    # Намеренно НЕ удаляем cookie `portal_auth_method` (ADR-036 п.7): она несёт
    # знание о способе входа для UX корректного re-login — после logout локальный
    # юзер должен снова попасть на /auth/local, а не на Keycloak SSO. Cookie
    # переживает logout и обновляется только на следующем login/callback.
    return redirect


@router.get("/logout", summary="GET logout (SLO front-channel)")
async def logout_get(
    redis: RedisDep,
    request: Request,
    response: Response,
) -> Response:
    # A3 — forced-logout (CSRF) protection. GET is a "safe" method and thus
    # skipped by the CSRF middleware, so a session-destroying GET could be
    # triggered cross-site (e.g. <img src=".../auth/logout">). Modern browsers
    # tag such cross-site sub-resource/iframe requests with
    # ``Sec-Fetch-Site: cross-site``; genuine same-origin navigations,
    # bookmarks (``none``) and same-site requests are not blocked.
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Cross-site logout rejected"},
        )

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await delete_session(redis, session_id)

    redirect = RedirectResponse(
        url="/auth/error?reason=logged_out", status_code=status.HTTP_302_FOUND
    )
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect
