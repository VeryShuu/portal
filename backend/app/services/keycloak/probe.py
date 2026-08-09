"""HTTP-пробы подключения к Keycloak для Admin UI (audit [M9]).

Diagnostic-эндпоинты «Проверить OIDC» / «Проверить sync» (кнопки в Admin UI →
«Keycloak»). Пробуют discovery + client_credentials (OIDC) и token + Admin API
users-list (sync), возвращают человекочитаемый результат для админа.

Вынесено из роутера ``app/api/keycloak_admin.py`` (God Module). Настройки
читаются через ``admin_store.load_settings``; URL уже валидирован роутером
через ``admin_store.validate_keycloak_url`` (allow-private). Все сетевые ошибки
ловятся и упаковываются в result (best-effort — probe не должен ронять UI).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.keycloak.admin_store import KeycloakSettings, load_settings

# Timeout для probe-запросов: Admin UI ждёт ответ интерактивно, длинный timeout
# подвешивает страницу. 10с хватает для discovery+token в корпоративной сети.
_PROBE_TIMEOUT = 10.0


async def test_oidc_connection() -> dict[str, Any]:
    """Проверить OIDC-клиент: discovery-эндпоинт + client_credentials токен.

    Возвращает dict с флагами ``discovery_ok``/``token_ok`` и человекочитаемыми
    ошибками. ``token_ok=None`` если client_id/secret не настроены (discovery
    проверен, но токен получить нельзя — информативно для админа).
    """
    s = load_settings()
    discovery_url = (
        f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}/.well-known/openid-configuration"
    )
    result: dict[str, Any] = {"discovery_url": discovery_url}

    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            data = resp.json()
            result["discovery_ok"] = True
            result["token_endpoint"] = data.get("token_endpoint")
            result["issuer"] = data.get("issuer")
    except Exception as exc:
        result["discovery_ok"] = False
        result["discovery_error"] = str(exc)
        return result

    if not s.oidc_client_id or not s.oidc_client_secret:
        result["token_ok"] = None
        result["token_note"] = "OIDC Client ID / Secret не настроены"
        return result

    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            token_resp = await client.post(
                result["token_endpoint"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": s.oidc_client_id,
                    "client_secret": s.oidc_client_secret,
                },
            )
            token_resp.raise_for_status()
            result["token_ok"] = True
    except httpx.HTTPStatusError as exc:
        result["token_ok"] = False
        result["token_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        result["token_ok"] = False
        result["token_error"] = str(exc)

    return result


async def test_sync_connection(
    *,
    sync_client_id: str | None = None,
    sync_client_secret: str | None = None,
) -> dict[str, Any]:
    """Проверить sync-клиент: токен + чтение 1 пользователя из Admin API.

    Опциональные ``sync_client_id``/``sync_client_secret`` позволяют проверить
    новые credentials **до сохранения** (передаются из тела запроса). Если не
    заданы — читаются из файла настроек. Возвращает dict с ``token_ok``/``users_ok``
    и подсказками (например про роль ``view-users`` при 403).
    """
    s = load_settings()
    sync_client_id = (sync_client_id if sync_client_id else None) or s.sync_client_id
    sync_client_secret = (
        sync_client_secret if sync_client_secret else None
    ) or s.sync_client_secret

    token_url = (
        f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}/protocol/openid-connect/token"
    )
    result: dict[str, Any] = {}

    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            token_resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": sync_client_id,
                    "client_secret": sync_client_secret,
                },
            )
            token_resp.raise_for_status()
            token = token_resp.json()["access_token"]
            result["token_ok"] = True
    except httpx.HTTPStatusError as exc:
        result["token_ok"] = False
        result["token_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        return result
    except Exception as exc:
        result["token_ok"] = False
        result["token_error"] = str(exc)
        return result

    admin_url = f"{s.keycloak_url.rstrip('/')}/admin/realms/{s.keycloak_realm}/users"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            users_resp = await client.get(
                admin_url,
                headers={"Authorization": f"Bearer {token}"},
                params={"first": 0, "max": 1, "briefRepresentation": "true"},
            )
            users_resp.raise_for_status()
            result["users_ok"] = True
            result["users_note"] = f"Получено {len(users_resp.json())} пользователей (тест)"
    except httpx.HTTPStatusError as exc:
        result["users_ok"] = False
        if exc.response.status_code == 403:
            result["users_error"] = (
                "403 Forbidden — убедитесь, что сервисному аккаунту назначена роль "
                "realm-management → view-users"
            )
        else:
            result["users_error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        result["users_ok"] = False
        result["users_error"] = str(exc)

    return result


def require_configured(s: KeycloakSettings) -> None:
    """Общий прекдишн probe-эндпоинтов: URL + Realm должны быть заданы.

    Раньше дублировался в роутере для oidc/sync; вынесен сюда (audit [M9]).
    """
    from fastapi import HTTPException, status

    if not s.keycloak_url or not s.keycloak_realm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keycloak URL и Realm должны быть заданы",
        )
