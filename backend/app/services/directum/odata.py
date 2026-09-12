"""Singleton ``httpx.AsyncClient`` для OData Directum + запросы задач.

Клон паттерна :mod:`app.services.max_messenger._client` (ленивый singleton,
инструментация метрик, типизированная ошибка + classify для ретраев).
Авторизация — basic auth (``auth=(username, password)`` на каждый запрос:
креды приходят из настроек и могут перечитываться без пересоздания клиента).

OData-запрос «Просроченные задачи» зашит в код (решение зафиксировано):
``GET {base_url}/IAssignments?$filter=Deadline lt {now} and Status eq 'InProcess'
&$select=Id,Subject,Deadline&$expand=Performer($select=Name)&$top=100&$skip=N``.
``Id`` добавлен к выборке пользователя — стабильная идентификация задачи в
отчётах (Subject+Performer могут дублироваться). Пагинация по ``$skip`` до
короткой страницы; ``MAX_PAGES`` защищает от бесконечной выборки.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.http_metrics import instrument_httpx_client
from app.core.logging import get_logger
from app.worker.tasks.email_utils import ErrorClass

logger = get_logger(__name__)

# Directum отвечает не быстро на развесистых $filter — read 15с; connect 5с
# (TLS-handshake во intranet почти мгновенный).
_DIRECTUM_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_DIRECTUM_LIMITS = httpx.Limits(max_keepalive_connections=2, max_connections=5)

# Системный trust store вместо certifi (в образ уже запечен Russian Trusted
# Root CA; публичные цепочки тоже резолвятся) — см. max_messenger/_client.py.
_DIRECTUM_SSL_CONTEXT = ssl.create_default_context()

_DIRECTUM_HTTP_CLIENT: httpx.AsyncClient | None = None

PAGE_SIZE = 100
# 50 страниц × 100 = 5000 задач — потолок защиты от зацикленной пагинации.
MAX_PAGES = 50

# Directum отдаёт метки со смещением +03:00; «сейчас» для $filter берём в той
# же зоне (зеркалит рабочий curl из задачи: date --iso-8601=seconds).
_MOSCOW = timezone(timedelta(hours=3))


def _get_client() -> httpx.AsyncClient:
    """Ленивый singleton — для путей вне FastAPI lifespan (тесты, воркер)."""
    global _DIRECTUM_HTTP_CLIENT
    if _DIRECTUM_HTTP_CLIENT is None or _DIRECTUM_HTTP_CLIENT.is_closed:
        _DIRECTUM_HTTP_CLIENT = instrument_httpx_client(
            httpx.AsyncClient(
                timeout=_DIRECTUM_TIMEOUT,
                limits=_DIRECTUM_LIMITS,
                verify=_DIRECTUM_SSL_CONTEXT,
                headers={"User-Agent": "portal-directum/1.0 (+odata)"},
            ),
            target="directum",
        )
    return _DIRECTUM_HTTP_CLIENT


async def init_directum_http_client() -> None:
    global _DIRECTUM_HTTP_CLIENT
    if _DIRECTUM_HTTP_CLIENT is None or _DIRECTUM_HTTP_CLIENT.is_closed:
        _DIRECTUM_HTTP_CLIENT = instrument_httpx_client(
            httpx.AsyncClient(
                timeout=_DIRECTUM_TIMEOUT,
                limits=_DIRECTUM_LIMITS,
                verify=_DIRECTUM_SSL_CONTEXT,
                headers={"User-Agent": "portal-directum/1.0 (+odata)"},
            ),
            target="directum",
        )


async def close_directum_http_client() -> None:
    global _DIRECTUM_HTTP_CLIENT
    if _DIRECTUM_HTTP_CLIENT is not None and not _DIRECTUM_HTTP_CLIENT.is_closed:
        await _DIRECTUM_HTTP_CLIENT.aclose()
    _DIRECTUM_HTTP_CLIENT = None


class DirectumApiError(Exception):
    """Non-2xx от OData или транспортный сбой. Несёт HTTP-статус (если был) —
    по нему sync/watchdog классифицируют ошибку через :func:`classify_error`."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DirectumTransportError(DirectumApiError):
    """Транспортный сбой (timeout/DNS/TLS) — всегда transient для ретраев."""


def classify_error(exc: BaseException) -> ErrorClass:
    """Классификация для решения «ретраить/чинить»: transient — сеть/5xx/429,
    permanent — остальные 4xx (креды/URL), unknown — прочее."""
    if isinstance(exc, DirectumTransportError):
        return "transient"
    status: int | None = getattr(exc, "status_code", None)
    if status is not None:
        if status == 429 or 500 <= status < 600:
            return "transient"
        if 400 <= status < 600:
            return "permanent"
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError):
        return "transient"
    return "unknown"


@dataclass(frozen=True)
class OverdueAssignment:
    """Одна просроченная задача из IAssignments."""

    id: str
    subject: str
    deadline: datetime
    performer_name: str


def now_directum() -> datetime:
    """«Сейчас» в зоне Directum (+03:00) — для $filter и расчёта просрочки."""
    return datetime.now(_MOSCOW)


def _parse_deadline(raw: Any) -> datetime:
    """ISO-строка OData → tz-aware datetime. Наивная трактуется как московское
    время (зона сервера Directum)."""
    dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_MOSCOW)
    return dt


def _parse_assignment(row: dict[str, Any]) -> OverdueAssignment:
    raw_performer = row.get("Performer")
    performer: dict[str, Any] = raw_performer if isinstance(raw_performer, dict) else {}
    # Id может отсутствовать у старых записей — синтезируем стабильный ключ из
    # содержания, чтобы отчёт/логи не теряли задачу.
    raw_id = row.get("Id")
    subject = str(row.get("Subject") or "").strip()
    task_id = str(raw_id) if raw_id else f"no-id:{subject}:{row.get('Deadline')}"
    return OverdueAssignment(
        id=task_id,
        subject=subject,
        deadline=_parse_deadline(row.get("Deadline")),
        performer_name=str(performer.get("Name") or "").strip(),
    )


async def _get_json(
    url: str, *, params: dict[str, Any], username: str, password: str
) -> dict[str, Any]:
    client = _get_client()
    try:
        resp = await client.get(url, params=params, auth=(username, password))
    except httpx.HTTPError as exc:
        # Транспорт (timeout/DNS/TLS) — обёртка без деталей, полный лог ниже.
        logger.warning("directum.odata.transport_error", error=type(exc).__name__)
        raise DirectumTransportError(
            f"Directum OData transport error: {type(exc).__name__}"
        ) from exc
    if resp.status_code >= 400:
        snippet = resp.text[:300]
        logger.warning("directum.odata.http_error", status=resp.status_code, snippet=snippet)
        raise DirectumApiError(
            f"Directum OData returned HTTP {resp.status_code}: {snippet}",
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise DirectumApiError("Directum OData returned non-JSON body") from exc
    if not isinstance(data, dict):
        raise DirectumApiError("Directum OData returned unexpected payload shape")
    return data


async def fetch_overdue_assignments(
    *, base_url: str, username: str, password: str, now: datetime | None = None
) -> list[OverdueAssignment]:
    """Все просроченные задачи в работе (``Status eq 'InProcess'``, дедлайн
    раньше ``now``), с пагинацией по ``$skip`` до короткой страницы."""
    url = f"{base_url.rstrip('/')}/IAssignments"
    now = now or now_directum()
    base_params: dict[str, Any] = {
        "$filter": f"Deadline lt {now.isoformat()} and Status eq 'InProcess'",
        "$select": "Id,Subject,Deadline",
        "$expand": "Performer($select=Name)",
        "$top": PAGE_SIZE,
    }
    items: list[OverdueAssignment] = []
    skip = 0
    for _page in range(MAX_PAGES):
        data = await _get_json(
            url, params={**base_params, "$skip": skip}, username=username, password=password
        )
        values = data.get("value")
        if not isinstance(values, list):
            raise DirectumApiError("Directum OData response has no 'value' array")
        for row in values:
            if isinstance(row, dict):
                items.append(_parse_assignment(row))
        if len(values) < PAGE_SIZE:
            return items
        skip += PAGE_SIZE
    logger.warning("directum.odata.page_limit_reached", max_pages=MAX_PAGES, items=len(items))
    return items


async def ping(*, base_url: str, username: str, password: str) -> int:
    """Проверка доступности + кредов: ``GET IAssignments?$top=1&$select=Id``.

    Возвращает количество записей на пробной странице (0/1). Бросает
    :class:`DirectumApiError` — вызывающий код (API-эндпоинт /test) превращает
    её в человекочитаемую диагностику.
    """
    url = f"{base_url.rstrip('/')}/IAssignments"
    data = await _get_json(
        url,
        params={"$top": 1, "$select": "Id"},
        username=username,
        password=password,
    )
    values = data.get("value")
    return len(values) if isinstance(values, list) else 0
