"""Unit-тесты: SSRF-guard (app.core.net_guard).

Покрытие:
- is_public_ip: public/private/loopback/link-local/multicast/cloud-metadata (v4+v6)
- is_safe_remote_url: scheme/host/bare-IP/localhost/DNS-deferred (чистая функция)
- resolve_all_ips: bare-IP fast-path + async-DNS (mock getaddrinfo)
- assert_url_safe: композиция URL-check + резолв (all-must-be-public)
- resolve_stable_ip: double-resolve против DNS-rebinding (TOCTOU)
"""

from __future__ import annotations

import ipaddress
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")

from app.core.net_guard import (
    assert_url_safe,
    is_public_ip,
    is_safe_remote_url,
    resolve_all_ips,
    resolve_stable_ip,
)

# ── is_public_ip ──────────────────────────────────────────────────────────────


class TestIsPublicIp:
    @pytest.mark.parametrize(
        "ip",
        ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2001:4860:4860::8888"],
    )
    def test_public_allowed(self, ip):
        assert is_public_ip(ipaddress.ip_address(ip)) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "127.0.0.1",
            "169.254.169.254",  # cloud-metadata (link-local /16)
            "169.254.1.1",  # link-local
            "224.0.0.1",  # multicast
            "0.0.0.0",  # unspecified
            "::1",  # IPv6 loopback
            "fc00::1",  # IPv6 ULA (private)
            "fe80::1",  # IPv6 link-local
            "fd00:ec2::254",  # AWS IMDS IPv6 (cloud-metadata, ULA — НЕ link-local)
        ],
    )
    def test_blocked_ranges_rejected(self, ip):
        assert is_public_ip(ipaddress.ip_address(ip)) is False


# ── is_safe_remote_url (чистая функция, без сети) ─────────────────────────────


class TestIsSafeRemoteUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/a.png",
            "http://example.com/favicon.ico",
            "https://8.8.8.8/x",  # public bare-IP
            "http://93.184.216.34/",
        ],
    )
    def test_allowed(self, url):
        assert is_safe_remote_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/x",
            "http://10.0.0.1/x",  # audit DoD
            "http://192.168.1.1/x",
            "http://172.16.0.1/x",
            "http://169.254.169.254/latest/meta-data/",  # cloud-metadata, audit DoD
            "http://[::1]/x",  # IPv6 loopback
            "http://[fc00::1]/x",  # IPv6 ULA
            "http://[fd00:ec2::254]/x",  # AWS IMDS IPv6
            "http://localhost/x",
            "http://0.0.0.0/x",  # blocked hostname (SSRF), не bind-адрес
        ],
    )
    def test_blocked(self, url):
        assert is_safe_remote_url(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://files.example.com/x",
            "gopher://x/y",
            "cid:abc",  # не network-схема
            "http:///nohost",  # пустой host
            "not a url at all",
        ],
    )
    def test_invalid_scheme_or_host(self, url):
        assert is_safe_remote_url(url) is False

    def test_domain_deferred_to_dns(self):
        """Доменные имена не блокируются на уровне URL — резолв в caller.

        Это намеренно: is_safe_remote_url — чистая функция, DNS-резолв
        выполняется отдельно (assert_url_safe / resolve_stable_ip), чтобы
        ловить случаи, когда домен резолвится в приватный IP.
        """
        assert is_safe_remote_url("http://internal.intranet.local/x") is True
        assert is_safe_remote_url("https://attacker.evil/") is True


# ── resolve_all_ips (async) ───────────────────────────────────────────────────
#
# Патчим app.core.net_guard.resolve_all_ips в тестах assert_url_safe /
# resolve_stable_ip — это надёжнее, чем патч asyncio.getaddrinfo (последний
# реализован через coroutine-обёртку и не перехватывается patch на классе loop).


def _ips_mock(*ips: str) -> AsyncMock:
    """AsyncMock для resolve_all_ips: возвращает IP-объекты для списка строк."""
    return AsyncMock(return_value=[ipaddress.ip_address(ip) for ip in ips])


class TestResolveAllIps:
    async def test_bare_ipv4_returns_itself(self):
        ips = await resolve_all_ips("8.8.8.8")
        assert ips == [ipaddress.ip_address("8.8.8.8")]

    async def test_bare_ipv6_returns_itself(self):
        ips = await resolve_all_ips("2001:4860:4860::8888")
        assert ips == [ipaddress.ip_address("2001:4860:4860::8888")]

    async def test_domain_resolves_to_multiple_ips(self):
        # Реальный DNS-резолв может вернуть несколько A-записей — проверяем,
        # что функция возвращает все уникальные IP (через patch getaddrinfo
        # на экземпляре loop внутри запущенного event-loop).
        async def fake_getaddrinfo(host, port, **kw):
            return [
                (0, 0, 0, "", ("93.184.216.34", 0)),
                (0, 0, 0, "", ("93.184.216.35", 0)),
            ]

        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo):
            ips = await resolve_all_ips("example.com")
        assert {str(ip) for ip in ips} == {"93.184.216.34", "93.184.216.35"}

    async def test_domain_unresolvable_returns_empty(self):
        async def boom(host, port, **kw):
            raise OSError("DNS NXDOMAIN")

        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", side_effect=boom):
            ips = await resolve_all_ips("nonexistent.invalid")
        assert ips == []

    async def test_dedupes_duplicate_ips(self):
        async def fake_getaddrinfo(host, port, **kw):
            return [
                (0, 0, 0, "", ("93.184.216.34", 0)),
                (0, 0, 0, "", ("93.184.216.34", 0)),
            ]

        import asyncio as _asyncio

        loop = _asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo):
            ips = await resolve_all_ips("example.com")
        assert len(ips) == 1


# ── assert_url_safe (композиция URL-check + DNS) ──────────────────────────────


class TestAssertUrlSafe:
    async def test_public_bare_ip_allowed(self):
        assert await assert_url_safe("http://8.8.8.8/x") is True

    async def test_private_bare_ip_blocked_without_dns(self):
        # bare-IP не доходит до резолва — блокируется на is_safe_remote_url.
        assert await assert_url_safe("http://10.0.0.1/x") is False

    async def test_cloud_metadata_blocked(self):
        assert await assert_url_safe("http://169.254.169.254/latest/meta-data/") is False

    async def test_domain_all_public_allowed(self):
        with patch(
            "app.core.net_guard.resolve_all_ips", _ips_mock("93.184.216.34", "93.184.216.35")
        ):
            assert await assert_url_safe("https://example.com/a") is True

    async def test_domain_any_private_blocked(self):
        # DNS-rebinding: одна запись public, другая private → блок.
        with patch("app.core.net_guard.resolve_all_ips", _ips_mock("93.184.216.34", "10.0.0.1")):
            assert await assert_url_safe("https://attacker.example.com/x") is False

    async def test_domain_unresolvable_blocked(self):
        with patch("app.core.net_guard.resolve_all_ips", new=AsyncMock(return_value=[])):
            assert await assert_url_safe("https://nonexistent.invalid/x") is False

    async def test_invalid_scheme_blocked_without_dns(self):
        with patch("app.core.net_guard.resolve_all_ips", new=AsyncMock()) as m:
            assert await assert_url_safe("file:///etc/passwd") is False
        m.assert_not_called()


# ── resolve_stable_ip (double-resolve против DNS-rebinding) ───────────────────


class TestResolveStableIp:
    async def test_bare_public_ip_stable(self):
        # bare-IP — один путь, без двойного резолва.
        ip = await resolve_stable_ip("8.8.8.8")
        assert ip == ipaddress.ip_address("8.8.8.8")

    async def test_bare_private_ip_returns_none(self):
        assert await resolve_stable_ip("10.0.0.1") is None

    async def test_domain_stable_public(self):
        # Оба резолва возвращают одно множество public IP → OK. resolve_stable_ip
        # фильтрует через is_public_ip сам, поэтому в mock можно включать и private
        # (они отфильтруются). Здесь даём только public — проверяем happy-path.
        with patch("app.core.net_guard.resolve_all_ips", _ips_mock("93.184.216.34")):
            ip = await resolve_stable_ip("example.com")
        assert str(ip) == "93.184.216.34"

    async def test_dns_rebinding_blocked(self):
        # Первый резолв public, второй private — классический rebinding.
        # resolve_stable_ip дважды вызывает resolve_all_ips и сравнивает множества
        # public-IP; side_effect эмулирует расхождение.
        with patch(
            "app.core.net_guard.resolve_all_ips",
            new=AsyncMock(
                side_effect=[
                    [ipaddress.ip_address("93.184.216.34")],
                    [ipaddress.ip_address("127.0.0.1")],
                ]
            ),
        ):
            ip = await resolve_stable_ip("attacker.evil")
        assert ip is None

    async def test_second_resolve_empty_blocked(self):
        # Первый public, второй пустой → блок.
        with patch(
            "app.core.net_guard.resolve_all_ips",
            new=AsyncMock(
                side_effect=[
                    [ipaddress.ip_address("93.184.216.34")],
                    [],
                ]
            ),
        ):
            ip = await resolve_stable_ip("attacker.evil")
        assert ip is None

    async def test_first_resolve_empty_blocked(self):
        with patch("app.core.net_guard.resolve_all_ips", new=AsyncMock(return_value=[])):
            ip = await resolve_stable_ip("nonexistent.invalid")
        assert ip is None
