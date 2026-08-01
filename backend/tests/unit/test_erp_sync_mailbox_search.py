"""Unit-тесты стратегии поиска и «не-трогания» флагов в erp_sync mailbox.

Защита от регрессии (фикс 2026-08-01): поллер обязан забирать **все** письма
папки (``SEARCH ALL``), а не только ``UNSEEN``. Ящик общий — его читают люди,
и любое прочитанное письмо получает ``\\Seen``; ``SEARCH UNSEEN`` молча терял
такие письма (реальный баг на проде). Дедупликация повторной обработки — на
уровне ``erp_sync_runs.message_id`` UNIQUE в :mod:`importer`, а НЕ через флаг
``\\Seen``. Портал не должен ставить ``\\Seen`` и не должен трогать письма
мимо фильтра.
"""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from app.services.erp_sync.mailbox import MailFilters, _process_uid, _search_all


class _FakeSearchClient:
    """Минимальный fake aioimaplib-клиента: только ``search``."""

    def __init__(self, *, typ: str, data: list) -> None:
        self._typ = typ
        self._data = data
        self.last_criterion: str | None = None

    async def search(self, criterion: str) -> tuple[str, list]:
        # Фиксируем критерий — тест фиксирует именно ALL, не UNSEEN.
        self.last_criterion = criterion
        return self._typ, self._data


async def test_search_all_returns_all_uids() -> None:
    client = _FakeSearchClient(typ="OK", data=[b"1 2 3"])
    uids = await _search_all(client)
    assert uids == ["1", "2", "3"]
    assert client.last_criterion == "ALL"


async def test_search_all_empty_when_no_messages() -> None:
    client = _FakeSearchClient(typ="OK", data=[b""])
    assert await _search_all(client) == []


async def test_search_all_empty_when_no_data() -> None:
    client = _FakeSearchClient(typ="OK", data=[])
    assert await _search_all(client) == []


async def test_search_all_empty_on_non_ok_status() -> None:
    # Сервер вернул NO/BUG — не падаем, отдаём пустой список.
    client = _FakeSearchClient(typ="NO", data=[b"1 2"])
    assert await _search_all(client) == []


@pytest.mark.parametrize("payload", [b"1 2 3", "1 2 3"])
async def test_search_all_handles_bytes_and_str(payload: object) -> None:
    """IMAP-ответы могут приходить как bytes — проверяем стойкость."""
    client = _FakeSearchClient(typ="OK", data=[payload])
    assert await _search_all(client) == ["1", "2", "3"]


# ── _process_uid: портал НЕ ставит \Seen и не трогает письма мимо фильтра ──


def _msg_with_attachment(
    *, subject: str, sender: str, message_id: str, filename: str = "report.txt"
) -> EmailMessage:
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = sender
    m["To"] = "portal@company.local"
    m["Message-ID"] = message_id
    m.set_content("See attachment")
    m.add_attachment(
        b"fio\tdate\tgender", maintype="application", subtype="octet-stream", filename=filename
    )
    return m


class _FakeProcessClient:
    """Fake aioimaplib-клиента для ``_process_uid``: фетч по UID + трекинг store."""

    def __init__(self, msg: EmailMessage) -> None:
        self._msg_bytes = msg.as_bytes()
        self.store_calls: list[tuple[str, str, str]] = []

    async def fetch(self, uid: str, what: str) -> tuple[str, list]:
        # Имитируем структуру aioimaplib-ответа: literal-маркер {NNN} + тело.
        n = len(self._msg_bytes)
        return "OK", [
            f"UID {uid} BODY[]".encode(),
            b"{" + str(n).encode() + b"}",
            self._msg_bytes,
            b")",
        ]

    async def store(self, uid: str, mode: str, flag: str) -> None:
        self.store_calls.append((uid, mode, flag))


async def test_process_uid_matching_does_not_mark_seen() -> None:
    """Подходящее письмо обрабатывается, но ``\\Seen`` НЕ ставится — маркер
    «обработано» это дедуп по message_id в БД, не почтовый флаг."""
    msg = _msg_with_attachment(
        subject="Отчет о днях рождения",
        sender="erp@mage.ru",
        message_id="<abc@erp>",
    )
    client = _FakeProcessClient(msg)
    candidate = await _process_uid(
        client,
        "28",
        filters=MailFilters(
            subject_filter="Отчет о днях рождения",
            sender_filter="erp@mage.ru",
            attachment_filter=".txt",
        ),
    )
    assert candidate is not None
    assert candidate.message_id == "<abc@erp>"
    # Ключевое: портал не меняет флаги в общем ящике.
    assert client.store_calls == []


async def test_process_uid_filtered_out_does_not_touch_mailbox() -> None:
    """Письмо мимо фильтра → пропускаем, не вызывая store (не трогаем ящик)."""
    msg = _msg_with_attachment(
        subject="Прайс-лист",  # мимо subject_filter
        sender="spam@spam.ru",
        message_id="<spam@x>",
    )
    client = _FakeProcessClient(msg)
    candidate = await _process_uid(
        client,
        "5",
        filters=MailFilters(subject_filter="Отчет о днях рождения", sender_filter=None),
    )
    assert candidate is None
    assert client.store_calls == []


async def test_process_uid_no_attachment_does_not_mark_seen() -> None:
    """Подошло по фильтру, но без вложения — пропускаем без ``\\Seen``
    (повторной обработки не будет: либо письмо без отчёта, либо importer
    удержит дедуп). Раньше здесь ставили Seen, чтобы «не крутить» — но на
    общем ящике это портило чужой inbox."""
    msg = EmailMessage()
    msg["Subject"] = "Отчет о днях рождения"
    msg["From"] = "erp@mage.ru"
    msg["Message-ID"] = "<no-attach@erp>"
    msg.set_content("no attachment here")
    client = _FakeProcessClient(msg)
    candidate = await _process_uid(
        client,
        "9",
        filters=MailFilters(subject_filter="Отчет", sender_filter="erp@"),
    )
    assert candidate is None
    assert client.store_calls == []


# ── delete_messages (delete_after_fetch, миграция 090) ─────────────────────


class _FakeDeleteClient:
    """Fake aioimaplib-клиента для ``delete_messages``: трекает store/expunge.

    ``store`` помечает UID как ``\\Deleted``; ``expunge`` фиксирует вызов.
    Не имеющие отношения методы (wait_hello_from_server/login/select/logout)
    — no-op корутины, т.к. ``delete_messages`` открывает своё подключение.
    """

    def __init__(self) -> None:
        self.store_calls: list[tuple[str, str, str]] = []
        self.expunge_called = False

    async def wait_hello_from_server(self) -> None:
        pass

    async def login(self, username: str, password: str) -> object:
        return "OK", [b"Login successful"]

    async def select(self, folder: str) -> object:
        return "OK", [b"[READ-WRITE] done"]

    async def store(self, uid: str, mode: str, flag: str) -> None:
        self.store_calls.append((uid, mode, flag))

    async def expunge(self) -> object:
        self.expunge_called = True
        return "OK", []

    async def logout(self) -> None:
        pass


def _patch_imap_client(monkeypatch, fake: _FakeDeleteClient) -> None:
    """Подменить ``_make_imap_client_raw`` на возврат fake-клиента.

    ``_make_imap_client_raw`` — синхронная функция (возвращает готовый клиент,
    не корутину), поэтому fake возвращаем синхронно."""
    from app.services.erp_sync import mailbox as mb

    def _factory(*, host: str, port: int, use_ssl: bool) -> _FakeDeleteClient:
        return fake

    monkeypatch.setattr(mb, "_make_imap_client_raw", _factory)


def _es():
    from app.schemas.branding import EmailSettings

    return EmailSettings(
        imap_host="mail.mage.ru",
        imap_port=993,
        imap_use_ssl=True,
        imap_username="portal@mage.ru",
        imap_password="secret",
        imap_folder="INBOX",
    )


async def test_delete_messages_marks_and_expunges(monkeypatch) -> None:
    """``delete_messages`` помечает UID'ы ``\\Deleted`` и зовёт ``EXPUNGE``."""
    fake = _FakeDeleteClient()
    _patch_imap_client(monkeypatch, fake)
    from app.services.erp_sync.mailbox import delete_messages

    deleted = await delete_messages(_es(), ["28", "42"])
    assert deleted == 2
    assert ("28", "+FLAGS", "\\Deleted") in fake.store_calls
    assert ("42", "+FLAGS", "\\Deleted") in fake.store_calls
    assert fake.expunge_called is True


async def test_delete_messages_empty_uids_noop(monkeypatch) -> None:
    """Пустой список UID → 0, подключение не открывается."""
    fake = _FakeDeleteClient()
    _patch_imap_client(monkeypatch, fake)
    from app.services.erp_sync.mailbox import delete_messages

    assert await delete_messages(_es(), []) == 0
    assert fake.store_calls == []
    assert fake.expunge_called is False


async def test_delete_messages_no_password_returns_zero(monkeypatch) -> None:
    """Нет IMAP-пароля → 0, без подключения (как fetch_unread_attachments)."""
    fake = _FakeDeleteClient()
    _patch_imap_client(monkeypatch, fake)
    from app.schemas.branding import EmailSettings
    from app.services.erp_sync.mailbox import delete_messages

    es = EmailSettings(imap_host="h", imap_username="u", imap_password="")
    assert await delete_messages(es, ["1"]) == 0
    assert fake.store_calls == []


async def test_delete_messages_continues_on_store_error(monkeypatch) -> None:
    """Падение STORE на один UID — warning, идём дальше; EXPUNGE зовётся
    для оставшихся. Письмо при ошибке остаётся в ящике, дедуп по message_id
    удержит повторную обработку (безопасно)."""
    fake = _FakeDeleteClient()
    _patch_imap_client(monkeypatch, fake)

    async def store(uid: str, mode: str, flag: str) -> None:
        if uid == "5":
            raise RuntimeError("STORE failed")
        fake.store_calls.append((uid, mode, flag))

    fake.store = store  # type: ignore[method-assign]
    from app.services.erp_sync.mailbox import delete_messages

    deleted = await delete_messages(_es(), ["5", "28"])
    # UID 5 упал → не посчитан; UID 28 — OK.
    assert deleted == 1
    assert fake.expunge_called is True
