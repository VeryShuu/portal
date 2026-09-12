"""SSRF-защита для outbound HTTP-запросов портала.

Единый модуль для валидации URL перед fetch'ем во внешнюю сеть: блокирует
private/loopback/link-local/multicast/unspecified/cloud-metadata адреса,
защищает от DNS-rebinding через двойной резолв с пиннингом IP.

Дизайн перенесён из ``app.services.helpdesk.email_images`` (лучшая реализация
в кодовой базе) и обобщён для переиспользования несколькими потребителями:
  * ``app.api.bookmarks._do_favicon_fetch`` (audit [H1] — favicon-прокси)
  * ``app.services.keycloak.probe`` / ``admin_store`` (audit [M9] — Keycloak,
    allow-private политика через ``is_safe_internal_url``)
  * (план) консолидация ``email_images._fetch_remote`` после стабилизации

Две политики:
  * **strict** (по умолчанию, ``is_public_ip``/``is_safe_remote_url``) — только
    public-адреса; для внешнего fetch (favicon, remote-картинки).
  * **allow-private** (``is_unsafe_internal_ip``/``is_safe_internal_url``) —
    private разрешён, блокируются loopback/link-local/multicast/cloud-metadata;
    для intranet-целей (Keycloak за VPN).

Все функции безопасны для async-контекста: DNS-резолв через
``asyncio.get_running_loop().getaddrinfo`` (раньше синхронный
``socket.getaddrinfo`` вешал event loop).

Ссылки по теме:
  * audit.md §[H1] — SSRF через /bookmarks/favicon (DoD: 10.0.0.1 → 404)
  * audit.md §[M9] — keycloak_admin God Module (консолидация SSRF)
"""

from __future__ import annotations

import asyncio
import ipaddress
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlparse

from app.core.logging import get_logger

logger = get_logger(__name__)

# Имена хостов, блокируемые всегда (нельзя отдать в getaddrinfo / ip_address).
# "0.0.0.0" здесь — блокируемое имя (SSRF-защита), не bind-адрес сервера.
_BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "ip6-localhost", "ip6-loopback", "0.0.0.0", "169.254.169.254"}  # nosec B104
)

# IPv6-эквивалент cloud-metadata (AWS IMDS): не покрывается is_link_local,
# проверяется явно. Слито из keycloak_admin._CLOUD_METADATA_NETS (audit [M9]).
_CLOUD_METADATA_V6 = ipaddress.ip_network("fd00:ec2::254/128")
_CLOUD_METADATA_V4 = ipaddress.ip_network("169.254.169.254/32")


def is_unsafe_internal_ip(ip: IPv4Address | IPv6Address) -> bool:
    """``True`` для адресов, запрещённых даже в allow-private политике (Keycloak).

    Блокирует loopback, link-local, multicast, unspecified и cloud-metadata
    (AWS IMDS v4 ``169.254.169.254`` + v6 ``fd00:ec2::254``). Приватные
    диапазоны (10.x, 172.16-31.x, 192.168.x, fc00::/7) **разрешены** — Keycloak
    обычно развёрнут за корпоративным VPN. IPv4-mapped IPv6 нормализуются.

    Перенесено из ``app.api.keycloak_admin._is_unsafe_ip`` (audit [M9] —
    консолидация SSRF в едином модуле). Семантически дополняет ``is_public_ip``
    (strict): здесь разрешаем private, там — нет.
    """
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip in _CLOUD_METADATA_V4
        or ip in _CLOUD_METADATA_V6
    )


def is_safe_internal_url(url: str) -> bool:
    """SSRF-валидатор для intranet-целей (Keycloak и т.п.) — allow-private.

    Контракт как у ``is_safe_remote_url`` (scheme http(s), непустой host,
    блокировка ``localhost``/``0.0.0.0``), но приватные диапазоны **разрешены** —
    блокируются только loopback/link-local/multicast/unspecified/cloud-metadata.
    DNS-резолв здесь не выполняется (чистая функция, как у ``is_safe_remote_url``)
    — для домена возвращает ``True`` (домен отдельно резолвится в caller'е).

    Используется для Keycloak, который типично развёрнут за VPN (см.
    ``keycloak_admin._validate_keycloak_url`` до задачи M9, audit [M9]).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or _is_blocked_hostname(host):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # домен — резолв в caller
    return not is_unsafe_internal_ip(ip)


def is_public_ip(ip: IPv4Address | IPv6Address) -> bool:
    """True для global-адресов (не private/loopback/link-local/multicast/...).

    ``is_global`` отлавливает большинство reserved-диапазонов, но НЕ покрывает
    multicast (224/4, ff00::/8): у них ``is_global=True``. Поэтому явно
    проверяем ``is_multicast`` — иначе атакующий мог бы направить запрос на
    multicast-адрес (поведение сети undefined, но не блокируется фильтром).
    """
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def _is_blocked_hostname(host: str) -> bool:
    return host in _BLOCKED_HOSTNAMES


def is_safe_remote_url(url: str) -> bool:
    """Разрешить fetch только public-адресов (защита от SSRF).

    Чистая функция (без сети, unit-тестируемая): проверяет схему http(s),
    непустой host, блокирует ``localhost``/``0.0.0.0`` и bare-IP из
    private/loopback/link-local диапазонов.

    DNS-резолв здесь НЕ выполняется намеренно — для доменных имён функция
    возвращает ``True`` (домен проверяется отдельно через ``resolve_*`` /
    ``assert_url_safe``, чтобы ловить DNS-rebinding и случаи, когда домен
    резолвится в приватный IP).
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
    if _is_blocked_hostname(host):
        return False
    # Если host — IP, проверяем диапазон. Домен — пропускаем (резолв в caller).
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return is_public_ip(ip)


async def resolve_all_ips(host: str) -> list[IPv4Address | IPv6Address]:
    """Резолв домена, вернуть список IP (async, не блокирует event loop).

    Для IP-адреса (не домена) возвращает его самого в одноэлементном списке.
    Возвращает пустой список, если host не резолвится (``OSError``) или
    содержит не-IP-мусор в ответе (``ValueError``). Фильтрации по диапазону
    здесь нет — caller решает политику (например, ``is_public_ip``).
    """
    try:
        ip = ipaddress.ip_address(host)
        return [ip]
    except ValueError:
        pass  # Домен — резолвим ниже.

    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
    except OSError:
        return []

    result: list[IPv4Address | IPv6Address] = []
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip not in result:
            result.append(ip)
    return result


async def assert_url_safe(url: str) -> bool:
    """Полная SSRF-проверка URL: scheme + host + DNS-резолв.

    Композиция ``is_safe_remote_url`` (scheme + bare-IP) и резолва домена:
    для доменного имени требует, чтобы ВСЕ A/AAAA-записи были public
    (защита от DNS-rebinding, где домен резолвится в 127.0.0.1).

    Используется на каждом hop редиректа, а не только на исходном URL — иначе
    редирект на internal/loopback/169.254.169.254 bypass'ил бы первичную
    валидацию (см. bookmarks._do_favicon_fetch, email_images._fetch_remote).
    """
    if not is_safe_remote_url(url):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    # bare-IP уже проверен в is_safe_remote_url.
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    ips = await resolve_all_ips(host)
    if not ips:
        return False
    return all(is_public_ip(ip) for ip in ips)


async def resolve_stable_ip(host: str) -> IPv4Address | IPv6Address | None:
    """Двойной резолв с пиннингом IP (защита от DNS-rebinding, TOCTOU).

    ``assert_url_safe`` резолвит host отдельно от httpx-соединения →
    классический TOCTOU: атакующий DNS (low TTL) может отдать public IP для
    проверки и ``127.0.0.1`` / ``169.254.169.254`` для реального соединения.
    Здесь резолвим **дважды** и требуем, чтобы оба резолва вернули одно и то
    же непустое множество public IP — сужает окно TOCTOU и блокирует базовый
    rebinding (первый ответ public, второй — private). Возвращает первый
    стабильный public IP или ``None``.

    Ограничение: теоретически уязвима к атакующему, полностью контролирующему
    DNS резолвер и держащему стабильный private-ответ после первого public.
    Полная защита требует пиннинга соединения на уровне httpcore transport —
    для корпоративного интранет-портала текущая защита достаточна
    (обоснование см. в audit.md §[H1]).
    """
    # bare-IP — стабилен по определению, проверен в is_safe_remote_url.
    try:
        ip = ipaddress.ip_address(host)
        return ip if is_public_ip(ip) else None
    except ValueError:
        pass

    first = [ip for ip in await resolve_all_ips(host) if is_public_ip(ip)]
    if not first:
        return None
    second = [ip for ip in await resolve_all_ips(host) if is_public_ip(ip)]
    if not second:
        return None
    first_set = {str(ip) for ip in first}
    second_set = {str(ip) for ip in second}
    if first_set != second_set:
        logger.warning(
            "net_guard.dns_rebinding_blocked",
            host=host,
            first=sorted(first_set),
            second=sorted(second_set),
        )
        return None
    return first[0]
