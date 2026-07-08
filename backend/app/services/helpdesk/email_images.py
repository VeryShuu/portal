"""Локализация картинок входящего email-письма при IMAP-ingress.

Проблема: картинки в письмах бывают трёх типов, и без локализации все ломаются:

1. **Inline ``cid:``** (``multipart/related``, ``Content-ID``) — ingress их не
   разбирает (бинарь не сохраняется), ``nh3`` дропает ``cid:`` из ``src`` →
   битая иконка.
2. **Внешние ``http://``** — блокируются CSP ``img-src 'self' data: blob: https:``
   (нет ``http:``).
3. **Внешние ``https://``** — работают, но утекают адрес получателя на внешние
   серверы (tracking-pixels), плюс mixed-content при https-портале.

Решение (Zammad/Freshdesk-подход): при ingress **локализовать** все картинки —
inline ``cid:`` и внешние ``http(s)://`` — сохранять в локальный FS как
``HelpdeskAttachment`` (привязанные к message), и переписывать ``src`` в
``body_html`` на относительный ``/api/v1/helpdesk/attachments/{id}``. Тогда:

* все img-src становятся относительными → подпадают под CSP ``'self'`` (CSP
  менять не нужно);
* нет утечки адресов получателей (tracking-pixels не срабатывают);
* нет mixed-content / plaintext-HTTP проблем;
* картинки переживают удаление из почтового ящика.

Чистые функции (extract, rewrite, SSRF-check) тестируются без БД;
``localize_images`` — async с db/httpx (мокируется в тестах).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import uuid
from email.message import Message
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

from app.core.logging import get_logger

logger = get_logger(__name__)

# Префикс rewritten-src: относительный путь к endpoint скачивания вложений.
ATTACHMENT_URL_PREFIX = "/api/v1/helpdesk/attachments/"

# Таймаут httpx-выкачки внешней картинки.
_FETCH_TIMEOUT = 10.0
# Лимит размера при стриминговой выкачке (защита от гигантских файлов —
# ``HELPDESK_MAX_ATTACHMENT_MB`` checked again в ``save_image_bytes``).
_FETCH_MAX_BYTES = 25 * 1024 * 1024

# User-Agent для выкачки (некоторые сервера отклоняют без него).
_UA = "Portal-Helpdesk-ImageProxy/1.0"


class InlineImage:
    """Inline-картинка из ``multipart/related`` (``Content-ID``)."""

    __slots__ = ("content_type", "data", "filename")

    def __init__(self, *, data: bytes, content_type: str, filename: str) -> None:
        self.data = data
        self.content_type = content_type
        self.filename = filename


# ── Extract inline parts (чистая функция) ────────────────────────────────────


def extract_inline_parts(msg: Message) -> dict[str, InlineImage]:
    """Собрать inline-картинки письма (``Content-ID`` → :class:`InlineImage`).

    ``multipart/related`` несёт HTML-тело + inline-части (картинки), на которые
    тело ссылается через ``<img src="cid:...">``. Идём по ``msg.walk()``, берём
    части с непустым ``Content-ID`` и ``image/*``. CID нормализуется: снимаем
    угловые скобки ``<...>``, приводим к нижнему регистру (RFC 2392 case-insensitive)."""
    result: dict[str, InlineImage] = {}
    for part in msg.walk():
        cid = part.get("Content-ID")
        if not cid:
            continue
        ctype = part.get_content_type()
        if not ctype.startswith("image/"):
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        key = _normalize_cid(cid)
        if not key:
            continue
        filename = part.get_filename() or f"inline-{key[:8] or uuid.uuid4().hex[:8]}"
        result[key] = InlineImage(
            data=bytes(payload), content_type=ctype, filename=filename
        )
    return result


def _normalize_cid(cid: str) -> str:
    """Убрать угловые скобки и привести к нижнему регистру (как ``<img src=cid:...>``
    ссылается). Возвращает ``""`` для пустого."""
    return cid.strip().strip("<>").strip().lower()


# ── Rewrite <img src> (чистые функции) ───────────────────────────────────────

# Находим все <img ... src="..." ...>. Атрибуты могут быть в любом порядке,
# кавычки двойные/одиночные/без. Группы 2/3/4 — сам URL (по типу кавычки).
_IMG_SRC_RE = re.compile(
    r"""(<img\b[^>]*?\bsrc=)(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    re.IGNORECASE,
)


def find_img_sources(html: str) -> list[str]:
    """Список всех URL из ``<img src="...">`` (в порядке появления). Для тестов."""
    sources: list[str] = []
    for m in _IMG_SRC_RE.finditer(html or ""):
        url = m.group(2) or m.group(3) or m.group(4) or ""
        sources.append(url)
    return sources


def replace_img_src(html: str, old_src: str, new_src: str) -> str:
    """Заменить первое вхождение ``old_src`` в ``<img src>`` на ``new_src``."""
    return (html or "").replace(old_src, new_src, 1)


# ── SSRF guard (чистая функция) ──────────────────────────────────────────────


def is_safe_remote_url(url: str) -> bool:
    """Разрешить выкачку только public-адресов (защита от SSRF).

    Блокируем private/loopback/link-local/multicast/reserved. DNS-резолв здесь
    НЕ выполняется (чистая функция для тестов) — проверяем только схему и
    host-как-IP; доменные имена проверяются в ``_fetch_remote`` через resolve.
    Возвращает ``False`` для не-http(s), bare-IP из private-диапазонов и
    ``localhost``.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost",):
        return False
    # Если host — IP, проверяем диапазон.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Доменное имя — резолв в ``_fetch_remote``; здесь пропускаем.
        return True
    return _is_public_ip(ip)


def _is_public_ip(ip: IPv4Address | IPv6Address) -> bool:
    """True для global-адресов (не private/loopback/link-local/и т.п.)."""
    return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local)


async def _resolve_is_safe(host: str) -> bool:
    """Резолв домена и проверить, что ВСЕ A/AAAA-записи public (защита от
    DNS-rebinding: домен резолвится в 127.0.0.1)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not _is_public_ip(ip):
            return False
    return True


# ── Localize (async: db + httpx) ─────────────────────────────────────────────


async def localize_images(
    db: AsyncSession,
    *,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    html: str,
    inline_map: dict[str, InlineImage],
    total_tracker: _TotalTrackerLike | None = None,
    save: _SaveFn | None = None,
) -> str:
    """Локализовать все ``<img>`` в ``html``: inline ``cid:`` и внешние ``http(s)://``.

    Для каждого ``src``:
      * ``cid:xxx`` → найти в ``inline_map``, сохранить как attachment (через
        ``save``), переписать src на ``/api/v1/helpdesk/attachments/{id}``.
      * ``http(s)://...`` → SSRF-проверка + httpx-выкачка, сохранение, переписать src.
        Best-effort: при ошибке/недоступности — оставить исходный URL (CSP
        пропустит https; http останется битым, но не уронит ingest).

    Возвращает обновлённый ``html``. Best-effort: ни одна картинка не роняет
    обработку письма. ``save`` по умолчанию — ``attachments.save_image_bytes``
    (ленивый импорт, для тестируемости можно подставить мок).
    """
    if not html:
        return html
    if save is None:
        from app.services.helpdesk.attachments import save_image_bytes

        save = save_image_bytes

    updated = html
    # Трекинг использованных cid (для fallback-привязки неиспользованных
    # inline-частей к <img> без src — Outlook-кейс, когда cid: дропается из src).
    used_cids: set[str] = set()
    for src in find_img_sources(html):
        if not src:
            continue
        new_src = await _localize_one(
            db,
            src=src,
            ticket=ticket,
            message=message,
            inline_map=inline_map,
            save=save,
            total_tracker=total_tracker,
            used_cids=used_cids,
        )
        if new_src and new_src != src:
            updated = replace_img_src(updated, src, new_src)

    # Fallback: неиспользованные inline-части (cid не сматчился в HTML, т.к.
    # Outlook дропает cid: из src, оставляя пустой <img>) привязать к <img> без
    # src — по порядку появления.
    updated = await _attach_orphan_inline(
        updated,
        db=db,
        ticket=ticket,
        message=message,
        inline_map=inline_map,
        used_cids=used_cids,
        save=save,
        total_tracker=total_tracker,
    )
    return updated


async def _localize_one(
    db: AsyncSession,
    *,
    src: str,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    inline_map: dict[str, InlineImage],
    save: _SaveFn,
    total_tracker: _TotalTrackerLike | None,
    used_cids: set[str] | None = None,
) -> str | None:
    """Локализовать один ``src``. Возвращает новый URL или ``None`` (оставить как есть)."""
    src_lower = src.strip().lower()
    if src_lower.startswith("cid:"):
        new_src = await _localize_cid(
            db,
            cid=src_lower[4:],
            inline_map=inline_map,
            ticket=ticket,
            message=message,
            save=save,
            total_tracker=total_tracker,
        )
        if new_src and used_cids is not None:
            used_cids.add(src_lower[4:])
        return new_src
    if src_lower.startswith(("http://", "https://")):
        return await _localize_remote(
            db,
            url=src,
            ticket=ticket,
            message=message,
            save=save,
            total_tracker=total_tracker,
        )
    # Относительные/data: — оставляем как есть (data: дропнет nh3; относительные
    # в письмах бессмысленны).
    return None


# Все <img> теги (для поиска тех, что без src — проверяется отдельно).
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# Атрибут src с непустым значением (для проверки «есть ли непустой src»).
_IMG_HAS_SRC_RE = re.compile(
    r'\bsrc\s*=\s*["\'](?!\s*["\'])', re.IGNORECASE
)


async def _attach_orphan_inline(
    html: str,
    *,
    db: AsyncSession,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    inline_map: dict[str, InlineImage],
    used_cids: set[str],
    save: _SaveFn,
    total_tracker: _TotalTrackerLike | None,
) -> str:
    """Привязать неиспользованные inline-части к ``<img>`` без ``src``.

    Outlook-кейс: ``<img src="cid:xxx">`` приходит как ``<img>`` (cid дропнут).
    inline-часть с Content-ID существует в ``inline_map``, но не сматчилась
    (нет cid: в HTML). Привязываем такие «осиротевшие» части к ``<img>`` без src
    по порядку появления — каждый orphan-<img> получает следующий неиспользованный
    inline. Best-effort: если orphan-<img> больше, чем inline-частей — лишние
    остаются битыми (нечем заполнить)."""
    if not inline_map or not html:
        return html
    orphan_cids = [c for c in inline_map if c not in used_cids]
    if not orphan_cids:
        return html

    # Найдём все <img> без src (или с пустым src), и для каждого асинхронно
    # сохраним orphan-inline.
    matches = [
        m for m in _IMG_TAG_RE.finditer(html) if not _IMG_HAS_SRC_RE.search(m.group(0))
    ]
    if not matches:
        return html
    # Соберём new_src для каждого матча (асинхронно), затем пересоберём html.
    new_srcs: list[str | None] = []
    cid_iter = iter(orphan_cids)
    for _ in matches:
        cid = next(cid_iter, None)
        if cid is None:
            new_srcs.append(None)
            continue
        att = await save(
            db,
            ticket=ticket,
            message_id=message.id,
            data=inline_map[cid].data,
            original_name=inline_map[cid].filename,
            total_tracker=total_tracker,
        )
        used_cids.add(cid)
        new_srcs.append(
            f"{ATTACHMENT_URL_PREFIX}{att.id}" if att is not None else None
        )
    # Пересобираем html: вставляем src в каждый <img> без него. Вставляем перед
    # закрывающим > или /> (сохраняя структуру тега).
    result_parts: list[str] = []
    last_end = 0
    for m, new_src in zip(matches, new_srcs, strict=False):
        if new_src is None:
            continue
        result_parts.append(html[last_end : m.start()])
        tag = m.group(0)
        # Уберём возможный пустой src="" (если был) перед вставкой нового.
        tag_clean = re.sub(r'\s*src\s*=\s*""', "", tag, flags=re.IGNORECASE)
        if tag_clean.endswith("/>"):
            result_parts.append(tag_clean[:-2] + f' src="{new_src}"/>')
        else:
            result_parts.append(tag_clean[:-1] + f' src="{new_src}">')
        last_end = m.end()
    result_parts.append(html[last_end:])
    return "".join(result_parts)


async def _localize_cid(
    db: AsyncSession,
    *,
    cid: str,
    inline_map: dict[str, InlineImage],
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    save: _SaveFn,
    total_tracker: _TotalTrackerLike | None,
) -> str | None:
    inline = inline_map.get(cid)
    if inline is None:
        return None
    att = await save(
        db,
        ticket=ticket,
        message_id=message.id,
        data=inline.data,
        original_name=inline.filename,
        total_tracker=total_tracker,
    )
    if att is None:
        return None
    return f"{ATTACHMENT_URL_PREFIX}{att.id}"


async def _localize_remote(
    db: AsyncSession,
    *,
    url: str,
    ticket: HelpdeskTicket,
    message: HelpdeskMessage,
    save: _SaveFn,
    total_tracker: _TotalTrackerLike | None,
) -> str | None:
    if not is_safe_remote_url(url):
        logger.warning("helpdesk.image.remote.unsafe_url", url=url)
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    # Для доменных имён — резолв и проверка всех адресов (DNS-rebinding guard).
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not await _resolve_is_safe(host):
            logger.warning("helpdesk.image.remote.unsafe_resolve", host=host)
            return None

    data = await _fetch_remote(url)
    if data is None:
        return None
    att = await save(
        db,
        ticket=ticket,
        message_id=message.id,
        data=data,
        original_name=_derive_remote_filename(url),
        total_tracker=total_tracker,
    )
    if att is None:
        return None
    return f"{ATTACHMENT_URL_PREFIX}{att.id}"


async def _fetch_remote(url: str) -> bytes | None:
    """Выкачать внешнюю картинку (httpx), с таймаутом и лимитом размера.

    Возвращает ``None`` при ошибке/недоступности/превышении размера (best-effort)."""
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_FETCH_TIMEOUT),
            follow_redirects=True,
            headers={"User-Agent": _UA},
        ) as client, client.stream("GET", url) as resp:
            if resp.status_code != 200:
                logger.warning(
                    "helpdesk.image.remote.bad_status", url=url, status=resp.status_code
                )
                return None
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype and not ctype.startswith("image/"):
                logger.warning("helpdesk.image.remote.not_image", url=url, content_type=ctype)
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > _FETCH_MAX_BYTES:
                    logger.warning("helpdesk.image.remote.too_large", url=url)
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("helpdesk.image.remote.fetch_failed", url=url, error=str(exc))
        return None


def _derive_remote_filename(url: str) -> str:
    """Имя файла из URL (последний сегмент пути) или fallback ``image``."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else ""
    return name or "image"


# ── Типы для DI (тесты подставляют моки) ─────────────────────────────────────

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.helpdesk import HelpdeskAttachment, HelpdeskMessage, HelpdeskTicket

    _SaveFn = Callable[..., Awaitable[HelpdeskAttachment | None]]


class _TotalTrackerLike(Protocol):
    """Счётчик суммарного размера вложений (``attachments._TotalTracker``
    удовлетворяет)."""

    total: int
