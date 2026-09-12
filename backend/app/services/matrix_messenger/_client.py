"""Singleton ``httpx.AsyncClient`` for the Matrix Client-Server API (Synapse).

По образцу :mod:`app.services.max_messenger._client` (singleton, per-call токен,
транспорнтые ошибки → ``MatrixApiError``). Отличия Matrix:

* auth — ``Authorization: Bearer <access_token>`` (у MAX — голый токен);
* отправка — ``PUT /rooms/{roomId}/send/m.room.message/{txnId}``: ``txnId``
  даёт идемпотентность на стороне сервера (повтор с тем же txnId вернёт тот
  же ``event_id``, дубля не будет) — идеально для outbox-ретраев. В качестве
  txnId воркер использует UUID outbox-строки (стабилен между попытками);
* homeserver свой (``homeserver_url`` из настроек), не глобальный константный
  URL — все функции принимают его параметром;
* ошибки — JSON ``{"errcode": "M_...", "error": "..."}`` (спецификация CS API).

TLS: homeserver может стоять за внутренним CA — используем системный
SSL-контекст (``ssl.create_default_context()``), как и для MAX (см. комментарий
в ``max_messenger/_client.py``): он подхватывает системный CA-bundle и
сертификаты, добавленные через ``update-ca-certificates``.
"""

from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import quote

import httpx

from app.core.http_metrics import instrument_httpx_client
from app.core.logging import get_logger
from app.worker.tasks.email_utils import ErrorClass

logger = get_logger(__name__)

_MATRIX_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MATRIX_LIMITS = httpx.Limits(max_keepalive_connections=5, max_connections=10)

# Системный trust store вместо certifi (внутренний CA homeserver'а; см. докстринг).
_MATRIX_SSL_CONTEXT = ssl.create_default_context()

# Module-level singleton (lazy-init; см. max_messenger._client).
_MATRIX_HTTP_CLIENT: httpx.AsyncClient | None = None


def _client_kwargs() -> dict:
    """Общие kwargs для создания httpx.AsyncClient (singleton и lazy-init)."""
    return {
        "timeout": _MATRIX_TIMEOUT,
        "limits": _MATRIX_LIMITS,
        "verify": _MATRIX_SSL_CONTEXT,
        "headers": {"User-Agent": "portal-notifications/1.0 (+matrix-cs-api)"},
    }


def _get_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared Matrix httpx client."""
    global _MATRIX_HTTP_CLIENT
    if _MATRIX_HTTP_CLIENT is None or _MATRIX_HTTP_CLIENT.is_closed:
        _MATRIX_HTTP_CLIENT = instrument_httpx_client(
            httpx.AsyncClient(**_client_kwargs()), target="matrix"
        )
    return _MATRIX_HTTP_CLIENT


async def init_matrix_http_client() -> None:
    """Eagerly initialise the shared client (FastAPI lifespan startup)."""
    global _MATRIX_HTTP_CLIENT
    if _MATRIX_HTTP_CLIENT is None or _MATRIX_HTTP_CLIENT.is_closed:
        _MATRIX_HTTP_CLIENT = instrument_httpx_client(
            httpx.AsyncClient(**_client_kwargs()), target="matrix"
        )


async def close_matrix_http_client() -> None:
    """Close the shared client (FastAPI lifespan shutdown)."""
    global _MATRIX_HTTP_CLIENT
    if _MATRIX_HTTP_CLIENT is not None and not _MATRIX_HTTP_CLIENT.is_closed:
        await _MATRIX_HTTP_CLIENT.aclose()
    _MATRIX_HTTP_CLIENT = None


class MatrixApiError(Exception):
    """Raised when the Matrix CS API returns non-2xx or transport fails.

    Carries the HTTP status code and Matrix ``errcode`` (``M_LIMIT_EXCEEDED``,
    ``M_UNKNOWN_TOKEN``, ``M_FORBIDDEN`` …) so the outbox worker can classify
    the failure via :func:`classify_http_error`.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errcode: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errcode = errcode


def _auth_headers(access_token: str) -> dict[str, str]:
    """Matrix CS API: ``Authorization: Bearer <access_token>``."""
    # Strip — defense-in-depth: токены, сохранённые до валидатора схемы,
    # могут нести хвостовой пробел; h11 отвергает заголовки с
    # trailing-whitespace («Illegal header value») ещё до отправки.
    return {
        "Authorization": f"Bearer {access_token.strip()}",
        "Content-Type": "application/json",
    }


def _url(homeserver_url: str, path: str) -> str:
    return f"{homeserver_url.rstrip('/')}/_matrix/client/v3/{path.lstrip('/')}"


async def _request(
    *,
    method: str,
    url: str,
    access_token: str,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    """Выполнить запрос; транспортные ошибки обернуть в MatrixApiError."""
    client = _get_client()
    try:
        return await client.request(
            method,
            url,
            json=json_body,
            headers=_auth_headers(access_token),
        )
    except httpx.HTTPError as exc:
        # Transport-level: timeout, connection refused, DNS, TLS — обёртка,
        # чтобы воркер классифицировал как transient и ретраил.
        raise MatrixApiError(f"Matrix API transport error: {type(exc).__name__}") from exc


async def _raise_for_error(resp: httpx.Response) -> None:
    """Non-2xx → MatrixApiError со статусом и errcode из JSON-тела."""
    if resp.status_code < 400:
        return
    try:
        err = resp.json()
        errcode = err.get("errcode")
        msg = str(err.get("error") or errcode or resp.text)
    except Exception:
        errcode = None
        msg = resp.text or f"HTTP {resp.status_code}"
    raise MatrixApiError(
        f"Matrix API returned HTTP {resp.status_code}: {msg[:300]}",
        status_code=resp.status_code,
        errcode=errcode if isinstance(errcode, str) else None,
    )


def matrix_id_for_user(email: str, server_name: str) -> str:
    """MXID по конвенции: ``borzihin.vs@mage.ru`` → ``@borzihin.vs:matrix.mage.ru``.

    Localpart MXID чувствителен к регистру — берём из email всегда в lowercase.
    """
    localpart = email.split("@", 1)[0].strip().lower()
    return f"@{localpart}:{server_name.strip()}"


async def whoami(*, homeserver_url: str, access_token: str) -> dict[str, Any]:
    """``GET /account/whoami`` — проверить токен (200 ``{"user_id": ...}``)."""
    resp = await _request(
        method="GET",
        url=_url(homeserver_url, "account/whoami"),
        access_token=access_token,
    )
    await _raise_for_error(resp)
    data = resp.json()
    return data if isinstance(data, dict) else {"_raw": data}


async def send_message(
    *,
    homeserver_url: str,
    access_token: str,
    room_id: str,
    txn_id: str,
    body: str,
    formatted_body: str | None = None,
) -> dict[str, Any]:
    """Отправить ``m.room.message`` (msgtype ``m.text``) в комнату.

    ``txn_id`` — идемпотентный ключ (спека CS API): повторная отправка с тем
    же txnId вернёт тот же ``event_id`` без дублирования. ``body`` —
    обязательный plain-text fallback; ``formatted_body`` — опциональный HTML
    из whitelist'а Matrix (``format=org.matrix.custom.html``).
    """
    content: dict[str, Any] = {"msgtype": "m.text", "body": body}
    if formatted_body:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = formatted_body

    # room_id начинается с '!' — экранируем для path-сегмента.
    path = f"rooms/{quote(room_id, safe='')}/send/m.room.message/{quote(txn_id, safe='')}"
    resp = await _request(
        method="PUT",
        url=_url(homeserver_url, path),
        access_token=access_token,
        json_body=content,
    )
    await _raise_for_error(resp)
    try:
        data = resp.json()
    except Exception:
        # 2xx с не-JSON телом — нетипично; не роняем отправку (outbox mark_sent,
        # чтобы не зацикливать ретраи на парсинге). Лог — для разбора.
        logger.warning(
            "matrix_messenger.send_message.unexpected_response",
            room_id=room_id,
            status=resp.status_code,
            snippet=resp.text[:200],
        )
        return {"_raw": resp.text}
    return data if isinstance(data, dict) else {"_raw": data}


async def create_dm(
    *,
    homeserver_url: str,
    access_token: str,
    invite_user_id: str,
) -> str:
    """Создать персональную DM-комнату с пользователем (``POST /createRoom``).

    ``is_direct=true`` + ``trusted_private_chat`` — стандартные параметры DM
    (клиенты помечают комнату как личный диалог). Возвращает ``room_id``.
    """
    resp = await _request(
        method="POST",
        url=_url(homeserver_url, "createRoom"),
        access_token=access_token,
        json_body={
            "is_direct": True,
            "invite": [invite_user_id],
            "preset": "trusted_private_chat",
        },
    )
    await _raise_for_error(resp)
    data = resp.json()
    room_id = data.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        raise MatrixApiError(f"createRoom returned no room_id: {str(data)[:300]}")
    return room_id


async def get_direct_rooms(
    *,
    homeserver_url: str,
    access_token: str,
    bot_user_id: str,
) -> dict[str, list[str]]:
    """Прочитать account data ``m.direct`` бота — карту ``MXID → [room_id, ...]``.

    Это стандартное хранилище DM-комнат (его же ведут клиенты): бот увидит и
    комнаты, созданные пользователем вручную. ``404 M_NOT_FOUND`` (account
    data ещё не создан) — норма, возвращаем ``{}``.
    """
    path = f"user/{quote(bot_user_id, safe='')}/account_data/m.direct"
    resp = await _request(
        method="GET",
        url=_url(homeserver_url, path),
        access_token=access_token,
    )
    if resp.status_code == 404:
        return {}
    await _raise_for_error(resp)
    try:
        data = resp.json()
    except Exception:
        logger.warning(
            "matrix_messenger.get_direct_rooms.unexpected_response",
            status=resp.status_code,
            snippet=resp.text[:200],
        )
        return {}
    if not isinstance(data, dict):
        return {}
    # Оставляем только корректные записи {MXID: [room_id, ...]}.
    result: dict[str, list[str]] = {}
    for mxid, rooms in data.items():
        if isinstance(mxid, str) and mxid.startswith("@") and isinstance(rooms, list):
            valid = [r for r in rooms if isinstance(r, str)]
            if valid:
                result[mxid] = valid
    return result


async def set_direct_room(
    *,
    homeserver_url: str,
    access_token: str,
    bot_user_id: str,
    direct_map: dict[str, list[str]],
) -> None:
    """Записать целиком account data ``m.direct`` (read-modify-write на caller'е).

    Воркер держит distributed lock на диспетчеризацию, поэтому гонок на
    account data нет. Ошибки записи не фатальны для отправки (кэш можно
    перестроить) — но пробрасываем исключение, пусть вызывающий решает.
    """
    path = f"user/{quote(bot_user_id, safe='')}/account_data/m.direct"
    resp = await _request(
        method="PUT",
        url=_url(homeserver_url, path),
        access_token=access_token,
        json_body=direct_map,
    )
    await _raise_for_error(resp)


def classify_http_error(exc: BaseException) -> ErrorClass:
    """Classify a Matrix-API exception for outbox retry/DLQ decisions.

    Семантика зеркалит ``max_messenger.classify_http_error``:
    * transient — 429 (``M_LIMIT_EXCEEDED`` — подождать Retry-After),
      5xx, таймауты/сеть;
    * permanent — прочие 4xx: 401 ``M_UNKNOWN_TOKEN`` (токен отозван),
      403 ``M_FORBIDDEN`` (нет доступа в комнату), 400 (в т.ч. invite
      несуществующего локального пользователя — конвенция MXID из email
      не гарантирует, что аккаунт существует);
    * unknown — всё остальное.
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
        return "unknown"
    return "unknown"
