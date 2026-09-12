"""HTTP-клиент к сервисам согласования 1С (``…/hs/Auth/…``).

Клон паттерна :mod:`app.services.directum.odata` (ленивый singleton
``httpx.AsyncClient``, системный trust store — в образ запечён Russian
Trusted Root CA). Авторизация двухуровневая (вариант 2, ответ 1С-разработчика
2026-09-04):

1. ``GETTokenByLogin?Login=<email>`` — Basic служебной учётки Portal →
   ``{"Токен": …}`` (TTL 30 мин, не продлевается);
2. обычные методы — Basic + ``Profile=<токен>``.

Токен кэшируется в Redis (TTL 25 мин, запас до протухания); на 401 от 1С
инвалидируется и берётся один раз заново (тихий re-login при SSO дёшев).

Контракт ошибок 1С после пакета доработок: честные HTTP-коды + JSON
``{"Result": "OK"|"Error", "Code": …, "Message": …}``. Клиент терпит и
легаси (200 + сырой текст / 404 без тела): модуль стартует только после
внедрения пакета, но во время стыковки не должен падать неразборчиво.
"""

from __future__ import annotations

import base64
import contextlib
import re
import ssl
import time
from typing import Any

import httpx
from httpx import USE_CLIENT_DEFAULT

from app.core.http_metrics import instrument_httpx_client
from app.core.logging import get_logger
from app.schemas.approvals import (
    LEGACY_MANAGER_STAGE,
    SUPPLIER_ORDER_TYPE,
    ApprovalDocument,
    ApprovalHistoryItem,
    ApprovalManagerOption,
    ApprovalProduct,
)

logger = get_logger(__name__)

# Согласование в 1С — тяжёлая операция (проведение документа + фоновое
# задание): read 30с на обычные вызовы, вложения — до 120с (base64 в JSON).
_ERP_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_ERP_ATTACHMENT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
_ERP_LIMITS = httpx.Limits(max_keepalive_connections=2, max_connections=5)

# Системный trust store вместо certifi (см. max_messenger/_client.py).
_ERP_SSL_CONTEXT = ssl.create_default_context()

_ERP_HTTP_CLIENT: httpx.AsyncClient | None = None

# Токен 1С живёт 1799с (захардкожено на стороне 1С) и не продлевается —
# кэшируем с запасом, чтобы не протухал между вызовами партии.
_TOKEN_TTL_SECONDS = 1500
_TOKEN_CACHE_PREFIX = "approvals:token:"


def _get_client() -> httpx.AsyncClient:
    """Ленивый singleton — для путей вне FastAPI lifespan (тесты, воркер)."""
    global _ERP_HTTP_CLIENT
    if _ERP_HTTP_CLIENT is None or _ERP_HTTP_CLIENT.is_closed:
        _ERP_HTTP_CLIENT = instrument_httpx_client(
            httpx.AsyncClient(
                timeout=_ERP_TIMEOUT,
                limits=_ERP_LIMITS,
                verify=_ERP_SSL_CONTEXT,
                headers={"User-Agent": "portal-approvals/1.0"},
            ),
            target="erp_approvals",
        )
    return _ERP_HTTP_CLIENT


async def close_http_client() -> None:
    global _ERP_HTTP_CLIENT
    if _ERP_HTTP_CLIENT is not None and not _ERP_HTTP_CLIENT.is_closed:
        await _ERP_HTTP_CLIENT.aclose()
    _ERP_HTTP_CLIENT = None


class ErpApprovalsError(Exception):
    """Отказ 1С (non-2xx или Result=Error). Несёт HTTP-статус 1С, если был."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ErpTransportError(ErpApprovalsError):
    """Транспортный сбой (timeout/DNS/TLS) — «ERP недоступна», не «ERP отказала»."""


# ── Токен ───────────────────────────────────────────────────────────────────


def _token_cache_key(login: str) -> str:
    return f"{_TOKEN_CACHE_PREFIX}{login}"


async def _get_cached_token(redis: Any, login: str) -> str | None:
    if redis is None:
        return None
    try:
        token = await redis.get(_token_cache_key(login))
    except Exception:
        return None
    return str(token) if token else None


async def _cache_token(redis: Any, login: str, token: str) -> None:
    if redis is None:
        return
    try:
        await redis.set(_token_cache_key(login), token, ex=_TOKEN_TTL_SECONDS)
    except Exception:
        logger.warning("approvals.token_cache_write_failed")


async def invalidate_token(redis: Any, login: str) -> None:
    if redis is None:
        return
    with contextlib.suppress(Exception):
        await redis.delete(_token_cache_key(login))


def _norm_login(login: str) -> str:
    """Канонический логин портала для 1С: email в нижнем регистре, с доменом.

    Договорённость с 1С (2026-09-04): регистр соответствия «логин портала →
    Пользователь» сравнивает строки регистрочувствительно (PostgreSQL) —
    портал шлёт канонично lower(email), регистр в 1С заполняется так же.
    """
    return login.strip().lower()


async def _request_token(
    client: httpx.AsyncClient, token_base_url: str, auth: tuple[str, str], login: str
) -> str:
    """``GETTokenByLogin`` под служебной учёткой → токен пользователя.

    Метод требует пароля НЕ должен — 1С-сторона обязана пускать его только
    под учёткой портала (403 для всех остальных, 404 — логина нет в регистре
    соответствий). Ответ принимаем в обоих форматах: легаси
    ``{"Токен": …}`` и новый ``{"Result": true, "Token": …}``.

    Выдача токенов живёт на отдельном RootURL (миграция 116: 1С публикует
    ``…/hs/PortalAuth``, документы — ``…/hs/Auth``).
    """
    try:
        resp = await client.get(
            f"{token_base_url}/GETTokenByLogin",
            params={"Login": _norm_login(login)},
            auth=auth,
        )
    except httpx.HTTPError as exc:
        raise ErpTransportError(f"ERP недоступна: {exc.__class__.__name__}") from exc
    _raise_for_status(resp)
    payload = _json_or_text(resp)
    token = payload.get("Токен") or payload.get("Token") if isinstance(payload, dict) else None
    if not token:
        raise ErpApprovalsError("ERP не вернула токен", status_code=502)
    return str(token)


async def _ensure_token(
    client: httpx.AsyncClient,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    redis: Any,
) -> str:
    cached = await _get_cached_token(redis, login)
    if cached:
        return cached
    token = await _request_token(client, token_base_url, auth, login)
    await _cache_token(redis, login, token)
    return token


# ── Разбор ответов 1С ───────────────────────────────────────────────────────


def _json_or_text(resp: httpx.Response) -> Any:
    """Ответ 1С бывает JSON, а бывает сырой текст/JSON-set («{"Профиль не
    найден"}»). Пытаемся JSON, иначе возвращаем текст."""
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _erp_message(resp: httpx.Response) -> str:
    payload = _json_or_text(resp)
    if isinstance(payload, dict):
        message = payload.get("Message") or payload.get("message")
        if message:
            return str(message)
    text = payload if isinstance(payload, str) else str(payload)
    return text[:300].strip() or f"HTTP {resp.status_code}"


def _looks_json(resp: httpx.Response) -> bool:
    """1С отдаёт JSON-тела ошибок БЕЗ Content-Type заголовка (проверено на
    тест-базе) — судим по первому непробельному символу тела: WAF-бан-страница
    и текст платформы «Недостаточно прав» начинаются не с {/[."""
    return resp.text.lstrip()[:1] in ("{", "[")


def _body_says_token_invalid(resp: httpx.Response) -> bool:
    """v2.1.0.0: методы данных (очередь/вложения/согласование) отвечают
    HTTP 200 **всегда** — протухший/чужой токен это текст в теле, а не 401
    (честные коды остались только у GETTokenByLogin). Живой тест-контур даёт
    псевдо-JSON без ключей: «{\\nПользователь по токену не найден\\n}», в
    переписке 1С фигурировало и «Профиль не найден» — судим по подстроке
    «не найден» + «токен/профиль». Массив данных (нормальный ответ очереди)
    отпадает сразу, чтобы не ловить эти слова в данных документов."""
    if resp.status_code != 200:
        return False
    text = resp.text.lstrip()
    if text.startswith("["):
        return False
    lowered = text.lower()
    return "не найден" in lowered and ("профиль" in lowered or "токен" in lowered)


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        # Не-JSON тело на ошибке — это не контракт 1С, а WAF-бан-страница /
        # текст платформы «Недостаточно прав» / упавший IIS (чеклист 1С §1, §5).
        # Инфраструктурная ошибка (502-семантика), НЕ «документ чужой».
        if not _looks_json(resp):
            raise ErpTransportError(
                f"ERP вернула не-JSON ответ (HTTP {resp.status_code}): "
                "WAF/прокси/права публикации — см. логи 1С"
            )
        raise ErpApprovalsError(_erp_message(resp), status_code=resp.status_code)
    # 200: ошибка в теле (Result=false — новый контракт, Result="Error" —
    # промежуточная договорённость).
    payload = _json_or_text(resp)
    if isinstance(payload, dict) and (
        payload.get("Result") is False or str(payload.get("Result", "")).lower() == "error"
    ):
        raise ErpApprovalsError(
            str(payload.get("Message") or "Ошибка ERP"),
            status_code=int(payload.get("Code") or 502),
        )


# ── Нормализация DocumentsForApproval ───────────────────────────────────────


def _to_float(value: Any) -> float | None:
    """1С присылает числа строками с разделителями разрядов и запятой
    («1 234,56»), причём пробел — неразрывный (U+00A0/U+202F): обычный
    ``str.replace(" ", "")`` их не убирает и float падает (сумма документа
    и цены товаров «исчезали» — прод-кейс 2026-09-05). ``re \\s`` в
    unicode-режиме матчит все варианты пробелов."""
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"\s+", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _history_items(raw: Any) -> list[ApprovalHistoryItem]:
    items: list[ApprovalHistoryItem] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            ApprovalHistoryItem(
                period=str(entry.get("Период") or ""),
                user=str(entry.get("Пользователь") or ""),
                event=str(entry.get("Событие") or ""),
                comment=str(entry.get("Комментарий") or ""),
                stage=str(entry.get("ЭтапПроцесса") or ""),
            )
        )
    return _trim_finished_runs(items)


PROCESS_STARTED_EVENT = "Процесс запущен"


def _trim_finished_runs(items: list[ApprovalHistoryItem]) -> list[ApprovalHistoryItem]:
    """Оставить только текущий запуск согласования: всё до последнего
    «Процесс запущен» — остатки остановленного прогона (перезапуск
    создаёт в 1С новый экземпляр процесса, старые записи согласующему
    только шумят; решение владельца, 2026-09-05). Без метки «Процесс
    запущен» история не трогается."""
    for i in range(len(items) - 1, -1, -1):
        if items[i].event.strip() == PROCESS_STARTED_EVENT:
            return items[i:]
    return items


def _products(raw: Any, has_prices: bool) -> list[ApprovalProduct]:
    items: list[ApprovalProduct] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            ApprovalProduct(
                name=str(entry.get("Номенклатура") or ""),
                # «Получатель» — подразделение-получатель строки (v2.1.0.0).
                recipient=str(entry.get("Получатель") or ""),
                quantity=str(entry.get("Количество") or ""),
                # Внутренние заказы 1С отдаёт с нулевыми ценами (скрытие цен) —
                # нормализуем в None, чтобы UI честно скрыл колонку.
                price=_to_float(entry.get("Цена")) if has_prices else None,
                total=_to_float(entry.get("СуммаСНДС")) if has_prices else None,
            )
        )
    return items


def _requires_manager(doc: dict) -> bool:
    """Приоритет — вычисляемое поле «ТребуетсяОтветственный» из нового пакета
    1С; fallback — легаси-сверка текста последнего этапа (как в старом PHP)."""
    flag = doc.get("ТребуетсяОтветственный")
    if flag is not None:
        return bool(flag)
    if doc.get("НаименованиеДокумента") == SUPPLIER_ORDER_TYPE:
        return False
    history = doc.get("ИсторияСогласования") or []
    if not history or not isinstance(history[-1], dict):
        return False
    return str(history[-1].get("ЭтапПроцесса") or "") == LEGACY_MANAGER_STAGE


def _parse_document(doc: dict) -> ApprovalDocument:
    doc_type = str(doc.get("НаименованиеДокумента") or "")
    has_prices = doc_type == SUPPLIER_ORDER_TYPE
    return ApprovalDocument(
        guid=str(doc.get("GUID") or ""),
        doc_type=doc_type,
        number=str(doc.get("Номер") or ""),
        date=str(doc.get("Дата") or ""),
        organization=str(doc.get("Организация") or ""),
        manager=str(doc.get("Менеджер") or ""),
        comment=str(doc.get("Комментарий") or ""),
        contractor=str(doc["Контрагент"]) if doc.get("Контрагент") is not None else None,
        project=str(doc["Проект"]) if doc.get("Проект") is not None else None,
        amount=_to_float(doc.get("СуммаДокумента")),
        currency=str(doc["Валюта"]) if doc.get("Валюта") is not None else None,
        activity_direction=(
            str(doc["НаправлениеДеятельности"])
            if doc.get("НаправлениеДеятельности") is not None
            else None
        ),
        # 1С отдаёт пустую строку у документов без задачи СЭД, у внутренних
        # заказов поле может отсутствовать вовсе — оба случая в None.
        sed_url=(str(doc["СсылкаНаЗадачуСЭД"]).strip() or None)
        if doc.get("СсылкаНаЗадачуСЭД") is not None
        else None,
        requires_manager=_requires_manager(doc),
        has_prices=has_prices,
        history=_history_items(doc.get("ИсторияСогласования")),
        products=_products(doc.get("Товары"), has_prices),
        managers=[
            ApprovalManagerOption(
                guid=str(m.get("GUID") or ""), name=str(m.get("Наименование") or "")
            )
            for m in doc.get("Пользователи") or []
            if isinstance(m, dict) and m.get("GUID")
        ],
    )


def _parse_documents(payload: Any) -> list[ApprovalDocument]:
    if not isinstance(payload, list):
        return []
    return [_parse_document(doc) for doc in payload if isinstance(doc, dict)]


def _parse_attachments(payload: Any) -> list[dict[str, Any]]:
    """Сырой список вложений ( dict с ДвоичныеДанные/ИмяФайла/Расширение) —
    байты декодируем лениво, по индексу (детальная карточка тянет весь JSON,
    скачивание — декодирует только нужный файл)."""
    if not isinstance(payload, list):
        return []
    return [f for f in payload if isinstance(f, dict) and f.get("ИмяФайла") is not None]


def attachment_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("ИмяФайла") or "file")
    ext = str(entry.get("Расширение") or "").strip()
    if ext and not name.lower().endswith(f".{ext.lower()}"):
        name = f"{name}.{ext}"
    return name


def _decode_attachment(entry: dict[str, Any]) -> bytes:
    """``ДвоичныеДанные`` = «#base64:<…>» (встречаются переносы строк) → bytes."""
    raw = str(entry.get("ДвоичныеДанные") or "")
    marker = "#base64:"
    start = raw.find(marker)
    b64 = raw[start + len(marker) :] if start >= 0 else raw
    b64 = "".join(b64.split())
    try:
        return base64.b64decode(b64)
    except (ValueError, TypeError) as exc:
        raise ErpApprovalsError("Не удалось декодировать вложение", status_code=502) from exc


# ── Высокоуровневые операции ────────────────────────────────────────────────


def _auth(settings_user: str, settings_password: str) -> tuple[str, str]:
    if not settings_user or not settings_password:
        raise ErpApprovalsError("Модуль согласования не настроен", status_code=503)
    return (settings_user, settings_password)


async def _authorized_get(
    client: httpx.AsyncClient,
    *,
    url: str,
    params: dict[str, str],
    auth: tuple[str, str],
    base_url: str,
    token_base_url: str,
    login: str,
    redis: Any,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    """GET с токеном из кэша; 401 → тихий re-request токена и один повтор
    (токен не продлевается — при длинной партии он протухает на середине).

    ``timeout=None`` (дефолт) означает «настройка клиента» (``_ERP_TIMEOUT``),
    а НЕ «без таймаутов»: в httpx явный ``None`` отключает все четыре
    таймаута, перекрывая клиентские настройки, поэтому наружу отдаётся
    sentinel ``USE_CLIENT_DEFAULT`` (ревью 2026-09-05). Транспортные сбои
    оборачиваются в ``ErpTransportError`` (как в ``_request_token``): сырой
    httpx-эксепшн не ловится ``except ErpApprovalsError`` ни в партии
    (терялся частичный отчёт), ни в одиночных эндпоинтах (500 вместо 502).
    """
    token = await _ensure_token(client, token_base_url, auth, login, redis)
    timeout_arg = timeout if timeout is not None else USE_CLIENT_DEFAULT

    async def _get() -> httpx.Response:
        try:
            return await client.get(
                url, params={**params, "Profile": token}, auth=auth, timeout=timeout_arg
            )
        except httpx.HTTPError as exc:
            raise ErpTransportError(f"ERP недоступна: {exc.__class__.__name__}") from exc

    resp = await _get()
    # v2.1.0.0: протухший токен приходит как 200 с текстом в теле — 401 может
    # не прийти вовсе. Оба признака обрабатываем одинаково: тихий re-login и
    # один повтор (токен не продлевается — при длинной партии он протухает
    # на середине).
    if resp.status_code == 401 or _body_says_token_invalid(resp):
        await invalidate_token(redis, login)
        token = await _request_token(client, token_base_url, auth, login)
        await _cache_token(redis, login, token)
        # Тихий re-login — штатная ситуация (токен живёт 1799с и не
        # продлевается), но всплески говорят о проблемах кэша/партии.
        logger.info("approvals.token_reissued")
        resp = await _get()
    if _body_says_token_invalid(resp):
        # Не маскируем под пустые данные/успех: очередь должна показать
        # ошибку, а согласование — НЕ вернуть «согласовано» с текстом отказа.
        raise ErpApprovalsError(
            "ERP не приняла токен согласования (пользователь по токену не найден)",
            status_code=502,
        )
    return resp


async def get_documents(
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    redis: Any = None,
) -> list[ApprovalDocument]:
    login = _norm_login(login)
    client = _get_client()
    resp = await _authorized_get(
        client,
        url=f"{base_url}/DocumentsForApproval",
        params={},
        auth=auth,
        base_url=base_url,
        token_base_url=token_base_url,
        login=login,
        redis=redis,
    )
    _raise_for_status(resp)
    return _parse_documents(_json_or_text(resp))


async def get_attachments(
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    document_uuid: str,
    redis: Any = None,
) -> list[dict[str, Any]]:
    """Сырые вложения документа (токен 1С-сторона проверяет после пакета
    доработок; раньше не проверяла вовсе — см. находки безопасности)."""
    login = _norm_login(login)
    client = _get_client()
    resp = await _authorized_get(
        client,
        url=f"{base_url}/GETDocumentAttachments",
        params={"Document": document_uuid},
        auth=auth,
        base_url=base_url,
        token_base_url=token_base_url,
        login=login,
        redis=redis,
        timeout=_ERP_ATTACHMENT_TIMEOUT,
    )
    _raise_for_status(resp)
    return _parse_attachments(_json_or_text(resp))


async def get_attachment_file(
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    document_uuid: str,
    index: int,
    redis: Any = None,
) -> tuple[str, bytes]:
    entries = await get_attachments(base_url, token_base_url, auth, login, document_uuid, redis)
    if index < 0 or index >= len(entries):
        raise ErpApprovalsError("Вложение не найдено", status_code=404)
    entry = entries[index]
    return attachment_name(entry), _decode_attachment(entry)


async def _decision(
    *,
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    redis: Any,
    method: str,
    document_uuid: str,
    extra_params: dict[str, str],
) -> str:
    """GETAgreed/GETNotAgreed: токен + параметры → текст-подтверждение 1С."""
    client = _get_client()
    resp = await _authorized_get(
        client,
        url=f"{base_url}/{method}",
        params={"Document": document_uuid, **extra_params},
        auth=auth,
        base_url=base_url,
        token_base_url=token_base_url,
        login=login,
        redis=redis,
    )
    _raise_for_status(resp)
    payload = _json_or_text(resp)
    if isinstance(payload, dict):
        # Новый контракт: {"Result": true, "Message": "…"}. Message может
        # отсутствовать — показываем нейтральное «OK», а не строковое True.
        return str(payload.get("Message") or "OK")
    return str(payload or "OK")


async def approve(
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    document_uuid: str,
    *,
    comment: str = "",
    employee_guid: str | None = None,
    redis: Any = None,
) -> str:
    login = _norm_login(login)
    extra: dict[str, str] = {}
    if employee_guid:
        extra["Employee"] = employee_guid
    if comment:
        extra["Comment"] = comment
    return await _decision(
        base_url=base_url,
        token_base_url=token_base_url,
        auth=auth,
        login=login,
        redis=redis,
        method="GETAgreed",
        document_uuid=document_uuid,
        extra_params=extra,
    )


async def reject(
    base_url: str,
    token_base_url: str,
    auth: tuple[str, str],
    login: str,
    document_uuid: str,
    *,
    comment: str,
    redis: Any = None,
) -> str:
    login = _norm_login(login)
    return await _decision(
        base_url=base_url,
        token_base_url=token_base_url,
        auth=auth,
        login=login,
        redis=redis,
        method="GETNotAgreed",
        document_uuid=document_uuid,
        extra_params={"Comment": comment},
    )


async def ping(
    base_url: str, token_base_url: str, auth: tuple[str, str], login: str
) -> tuple[bool, str, int]:
    """Проверка подключения через ``GETTokenByLogin`` (email самого админа).

    Под честным контрактом профиль с фейковым токеном неотличим от отказа
    кредов (оба → 401 на документных методах), поэтому probe — токен-метод:

    * 200 — полная цепочка: WAF, креды Portal, сервис, маппинг логина;
    * 404 — креды/сервис в порядке, но этот логин не сопоставлен в регистре
      1С (покрытие 177/N) — это НЕ ошибка подключения;
    * 401 — учётка Portal не принята;
    * не-JSON — WAF/прокси/права публикации.
    """
    client = _get_client()
    started = time.monotonic()
    try:
        resp = await client.get(
            f"{token_base_url}/GETTokenByLogin",
            params={"Login": _norm_login(login)},
            auth=auth,
        )
    except httpx.HTTPError as exc:
        return False, f"ERP недоступна: {exc.__class__.__name__}", _ms(started)
    latency = _ms(started)
    if resp.status_code == 200:
        # 200 обязан нести токен по контракту (легаси {"Токен": …} или новый
        # {"Result": true, "Token": …}). HTML/пустое тело чужого сервера под
        # неверным адресом успехом НЕ считается (ревью 2026-09-05: ложный
        # зелёный ping до проверки тела).
        payload = _json_or_text(resp)
        token = payload.get("Токен") or payload.get("Token") if isinstance(payload, dict) else None
        if token:
            return True, "ERP доступна, учётка Portal принята, токен по логину выдан", latency
        excerpt = str(payload).strip()[:120]
        return (
            False,
            f"HTTP 200 без токена в теле — под адресом не сервис 1С (начало: {excerpt!r})",
            latency,
        )
    if resp.status_code == 404:
        # Легаси допускает 404 без тела («логин не сопоставлен»), но HTML-тело —
        # чужой сервер/неверная публикация: успехом не считается.
        if resp.text.lstrip()[:1] == "<":
            return (
                False,
                "HTTP 404 с HTML-телом — неверный адрес публикации (WAF/чужой сервер?)",
                latency,
            )
        return (
            True,
            "ERP доступна, учётка Portal принята; этот логин пока не сопоставлен "
            "в регистре 1С (404) — попросите 1С добавить его в соответствие",
            latency,
        )
    if resp.status_code == 401:
        return False, "ERP доступна, но учётка не принята (401) — проверьте пароль Portal", latency
    if not _looks_json(resp):
        return (
            False,
            f"Неожиданный не-JSON ответ 1С (HTTP {resp.status_code}): WAF/прокси/права?",
            latency,
        )
    return False, f"Неожиданный ответ 1С (HTTP {resp.status_code}): {_erp_message(resp)}", latency


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


# Пауза между документами массового согласования (совет 1С-разработчика:
# каждый GETAgreed — проведение документа + фоновое задание; не DDoS-ить).
BULK_APPROVE_PAUSE_SECONDS = 0.5
