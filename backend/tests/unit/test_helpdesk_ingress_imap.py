"""Unit tests for the isolated IMAP transport boundary."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.helpdesk import ingress_imap


def test_make_imap_client_raw_uses_ssl_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    ssl_client = MagicMock(return_value="ssl-client")
    plain_client = MagicMock(return_value="plain-client")
    monkeypatch.setitem(
        sys.modules, "aioimaplib", SimpleNamespace(IMAP4_SSL=ssl_client, IMAP4=plain_client)
    )

    assert (
        ingress_imap._make_imap_client_raw(host="imap.example", port=993, use_ssl=True)
        == "ssl-client"
    )
    assert (
        ingress_imap._make_imap_client_raw(host="imap.example", port=143, use_ssl=False)
        == "plain-client"
    )
    ssl_client.assert_called_once_with(host="imap.example", port=993)
    plain_client.assert_called_once_with(host="imap.example", port=143)


def test_make_imap_client_reads_mailbox_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_client = MagicMock(return_value="client")
    monkeypatch.setattr(ingress_imap, "_make_imap_client_raw", raw_client)
    settings = SimpleNamespace(imap_host="imap.example", imap_port=993, imap_use_ssl=True)

    assert ingress_imap._make_imap_client(settings) == "client"  # type: ignore[arg-type]
    raw_client.assert_called_once_with(host="imap.example", port=993, use_ssl=True)


class _ProbeClient:
    def __init__(self, response: object) -> None:
        self.wait_hello_from_server = AsyncMock()
        self.login = AsyncMock()
        self.select = AsyncMock(return_value=response)
        self.logout = AsyncMock()


async def test_probe_imap_connection_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _ProbeClient(("OK", []))
    monkeypatch.setattr(ingress_imap, "_make_imap_client_raw", MagicMock(return_value=client))

    assert await ingress_imap.probe_imap_connection(
        host="imap.example",
        port=993,
        username="user",
        password="secret",
        use_ssl=True,
        folder="INBOX",
    ) == (True, "Connected, selected 'INBOX'")
    client.logout.assert_awaited_once()


@pytest.mark.parametrize("response", [("NO", []), None])
async def test_probe_imap_connection_reports_select_failure(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    client = _ProbeClient(response)
    monkeypatch.setattr(ingress_imap, "_make_imap_client_raw", MagicMock(return_value=client))

    ok, detail = await ingress_imap.probe_imap_connection(
        host="imap.example",
        port=993,
        username="user",
        password="secret",
        use_ssl=True,
        folder="INBOX",
    )
    assert ok is False
    assert detail.startswith("select failed:")


async def test_probe_imap_connection_reports_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingress_imap, "_make_imap_client_raw", MagicMock(side_effect=RuntimeError("offline"))
    )

    assert await ingress_imap.probe_imap_connection(
        host="imap.example",
        port=993,
        username="user",
        password="secret",
        use_ssl=True,
        folder="INBOX",
    ) == (False, "RuntimeError: offline")


@pytest.mark.parametrize(
    ("function", "flag"),
    [(ingress_imap._safe_seen, "\\Seen"), (ingress_imap._safe_delete, "\\Deleted")],
)
async def test_safe_flag_marks_message(function: object, flag: str) -> None:
    client = SimpleNamespace(store=AsyncMock())

    await function(client, "42")  # type: ignore[operator]

    client.store.assert_awaited_once_with("42", "+FLAGS", flag)


@pytest.mark.parametrize("function", [ingress_imap._safe_seen, ingress_imap._safe_delete])
async def test_safe_flag_swallows_imap_error(function: object) -> None:
    client = SimpleNamespace(store=AsyncMock(side_effect=RuntimeError("offline")))

    await function(client, "42")  # type: ignore[operator]
    client.store.assert_awaited_once()
