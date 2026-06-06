"""OIDC Authorization Code + PKCE flow: ``/auth/login`` и ``/auth/callback``."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import text as sa_text

from app.api.deps import DbDep, RedisDep
from app.core.redirects import safe_redirect
from app.core.security import (
    SESSION_COOKIE_NAME,
    extract_user_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_session_id,
    generate_state,
    parse_jwt_claims,
)
from app.services import keycloak as kc_service
from app.services.audit import push_audit_event
from app.services.full_name_source import get_full_name_attr_key_sa, resolve_full_name
from app.services.session import (
    delete_session,
    get_and_delete_pkce_state,
    save_pkce_state,
    save_session,
)

from ._helpers import (
    _build_session_cookie_response,
    _callback_uri,
    _client_ip,
    _resolve_id_token_nonce,
    _sso_failure_redirect,
    _upsert_user,
    logger,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", summary="Redirect to Keycloak login")
async def login(
    redis: RedisDep,
    request: Request,
    redirect_after: str = Query(default="/", alias="redirect"),
) -> RedirectResponse:
    kcs = await kc_service._get_kc_settings_async(redis)
    if not kcs.keycloak_url or not kcs.keycloak_realm:
        logger.warning("auth.sso_not_configured")
        return await _sso_failure_redirect(redis, request, reason="sso_not_configured")

    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    state = generate_state()
    nonce = generate_state()

    safe_target = safe_redirect(redirect_after, default="/")
    await save_pkce_state(redis, state, verifier, nonce, safe_target)

    url = kc_service.get_authorization_url(
        redirect_uri=_callback_uri(),
        state=state,
        nonce=nonce,
        code_challenge=challenge,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback", summary="OIDC callback — exchange code for session")
async def callback(
    redis: RedisDep,
    db: DbDep,
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    # Phase 1: provider error short-circuit (code/state optional so an
    # error-only callback reaches this handler instead of a 422).
    if error:
        logger.warning(
            "OIDC error from provider",
            error=error,
            error_description=request.query_params.get("error_description"),
        )
        return await _sso_failure_redirect(
            redis, request, reason="oidc_error", extra={"error": error}
        )

    # Phase 1b: malformed callback without provider error (missing code/state).
    if not code or not state:
        logger.warning("auth.callback_missing_params")
        return await _sso_failure_redirect(
            redis, request, reason="oidc_error", extra={"error": "missing_params"}
        )

    # Phase 2: validate PKCE state.
    pkce = await get_and_delete_pkce_state(redis, state)
    if not pkce:
        return await _sso_failure_redirect(redis, request, reason="invalid_state")

    # Phase 3: exchange code for tokens.
    try:
        tokens = await kc_service.exchange_code_for_tokens(
            code=code,
            redirect_uri=_callback_uri(),
            code_verifier=pkce["verifier"],
        )
    except Exception as exc:
        logger.exception(
            "auth.token_exchange_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return await _sso_failure_redirect(redis, request, reason="token_exchange_failed")

    # Phase 4: parse access token JWT.
    jwks = await kc_service.get_jwks()
    try:
        claims = await parse_jwt_claims(tokens["access_token"], jwks)
    except Exception as exc:
        logger.exception(
            "auth.jwt_parse_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return await _sso_failure_redirect(redis, request, reason="jwt_invalid")

    # Phase 5: verify nonce (id_token preferred, access_token fallback).
    token_nonce = await _resolve_id_token_nonce(tokens, jwks, claims.get("nonce"))
    expected_nonce = pkce.get("nonce")
    if not expected_nonce or not token_nonce or expected_nonce != token_nonce:
        logger.warning(
            "auth.nonce_mismatch",
            expected=bool(expected_nonce),
            received=bool(token_nonce),
        )
        await push_audit_event(
            redis,
            event_type="auth.nonce_mismatch",
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            metadata={"state": state},
        )
        return await _sso_failure_redirect(redis, request, reason="nonce_mismatch")

    # Phase 6: upsert user.
    # Источник ФИО (user_attribute_mappings.is_full_name_source) применяется в
    # двух местах: (a) если Keycloak положил атрибут в JWT как top-level claim —
    # используем его сразу при upsert; (b) если в JWT его нет (типовой кейс,
    # когда mapper не настроен), но воркер sync уже положил значение в
    # users.attributes — перезаписываем full_name пост-фактум одним UPDATE по
    # текущему пользователю.  Так после первого же логина юзер видит полное
    # ФИО без ожидания следующего цикла Keycloak-синка.
    full_name_attr_key = await get_full_name_attr_key_sa(db)
    if full_name_attr_key:
        claims["name"] = resolve_full_name(
            default=claims.get("name", ""),
            kc_attrs=claims,
            attr_key=full_name_attr_key,
        )
    user_data = extract_user_data(claims)
    user_data["_email_verified"] = bool(claims.get("email_verified"))
    user, account_linked = await _upsert_user(db, user_data)
    if full_name_attr_key:
        await db.execute(
            sa_text(
                """
                UPDATE users
                SET full_name = btrim(attributes->>:k),
                    updated_at = NOW()
                WHERE id = :uid
                  AND attributes ? :k
                  AND btrim(coalesce(attributes->>:k, '')) <> ''
                  AND full_name IS DISTINCT FROM btrim(attributes->>:k)
                """
            ),
            {"k": full_name_attr_key, "uid": user.id},
        )
    await db.commit()

    # Phase 7: rotate session.
    old_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if old_session_id:
        await delete_session(redis, old_session_id)

    session_id = generate_session_id()
    await save_session(
        redis,
        session_id,
        {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "id_token": tokens.get("id_token"),
            "user_id": str(user.id),
            "keycloak_id": user.keycloak_id,
            "auth_source": "keycloak",
        },
    )

    # Phase 8: emit audit events.
    await push_audit_event(
        redis,
        event_type="auth.login",
        user_id=str(user.id),
        user_email=user.email,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        metadata={"source": "keycloak"},
    )
    if account_linked:
        await push_audit_event(
            redis,
            event_type="auth.account_linked",
            user_id=str(user.id),
            user_email=user.email,
            ip_address=_client_ip(request),
            metadata={"new_keycloak_id": user_data.get("keycloak_id")},
        )

    # Phase 9: build session-cookie redirect.
    redirect_target = safe_redirect(pkce.get("redirect_after"), default="/")
    return _build_session_cookie_response(redirect_target, session_id)
