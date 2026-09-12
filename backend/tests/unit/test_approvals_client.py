"""Unit-тесты ERP-клиента согласования (:mod:`app.services.approvals.client`).

httpx подменяется MockTransport-клиентом в module-global singleton (клон
``test_directum_odata.py``). Проверяются: выдача токена GETTokenByLogin,
кэш токена + тихий re-request на 401, нормализация кириллических полей
документов (ТребуетсяОтветственный / легаси-этап, скрытие цен), декодирование
base64-вложений, новый контракт ошибок и легаси-ответы, ping.
"""

from __future__ import annotations

import base64
from collections.abc import Callable

import httpx
import pytest

from app.services.approvals import client
from app.services.approvals.client import ErpApprovalsError, ErpTransportError

BASE = "https://erp.test/MageErp/hs/Auth"
TOKEN_BASE = "https://erp.test/MageErp/hs/PortalAuth"
AUTH = ("Portal", "pw")


@pytest.fixture(autouse=True)
async def _reset_client():
    yield
    if client._ERP_HTTP_CLIENT is not None:
        await client._ERP_HTTP_CLIENT.aclose()
    client._ERP_HTTP_CLIENT = None


def _with_token(handler: Callable, token: str = "tok") -> Callable:
    """Все высокоуровневые операции сначала запрашивают токен — заглушка
    обслуживает GETTokenByLogin сама, дальше отвечает handler."""

    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/GETTokenByLogin"):
            return httpx.Response(200, json={"Токен": token})
        return handler(request)

    return inner


def _install(handler: Callable, token: str = "tok") -> None:
    client._ERP_HTTP_CLIENT = httpx.AsyncClient(
        transport=httpx.MockTransport(_with_token(handler, token))
    )


def _install_raw(handler: Callable) -> None:
    """Без обёртки токена — для тестов самого GETTokenByLogin/повторов."""
    client._ERP_HTTP_CLIENT = httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeRedis:
    """Достаточное подмножество redis.asyncio для кэша токенов."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


def _doc_supplier(guid="g-1", **over):
    doc = {
        "GUID": guid,
        "НаименованиеДокумента": "ЗаказПоставщику",
        "Номер": "УП-0001",
        "Дата": "04.09.2026",
        "Организация": "МАГЭ",
        "Менеджер": "Иванов И.И.",
        "Контрагент": "ООО Поставщик",
        "Проект": "Проект-1",
        "СуммаДокумента": "1 234,56",
        "Валюта": "EUR",
        "Комментарий": "срочно",
        "ИсторияСогласования": [
            {
                "Период": "01.09.2026",
                "Пользователь": "Петя",
                "Событие": "Старт",
                "Комментарий": "",
                "ЭтапПроцесса": "Начало",
            }
        ],
        "Товары": [
            {"Номенклатура": "Болт М10", "Количество": 100, "Цена": 10.5, "СуммаСНДС": 1260},
        ],
        "Пользователи": [{"GUID": "m-1", "Наименование": "Сидоров С.С."}],
    }
    doc.update(over)
    return doc


def _doc_internal(guid="g-2", **over):
    doc = {
        "GUID": guid,
        "НаименованиеДокумента": "ЗаказНаВнутреннееПотребление",
        "Номер": "ВН-7",
        "Дата": "03.09.2026",
        "Организация": "МАГЭ",
        "Менеджер": "Отсутствует",
        "НаправлениеДеятельности": "Бурение",
        "Комментарий": "",
        "ИсторияСогласования": [],
        "Товары": [{"Номенклатура": "Смазка", "Количество": 2, "Цена": 0, "СуммаСНДС": 0}],
        "Пользователи": [],
    }
    doc.update(over)
    return doc


class TestToken:
    async def test_token_by_login(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/GETTokenByLogin")
            assert request.url.params["Login"] == "u@mage.ru"
            assert request.headers["Authorization"].startswith("Basic ")
            return httpx.Response(200, json={"Токен": "tok-1"})

        _install_raw(handler)
        token = await client._request_token(client._get_client(), TOKEN_BASE, AUTH, "u@mage.ru")
        assert token == "tok-1"

    async def test_token_new_contract_alias(self):
        # Новый контракт 1С: {"Result": true, "Token": …} — принимаем наравне
        # с легаси {"Токен": …}.
        _install_raw(lambda request: httpx.Response(200, json={"Result": True, "Token": "tok-new"}))
        token = await client._request_token(client._get_client(), TOKEN_BASE, AUTH, "U@Mage.RU")
        assert token == "tok-new"

    async def test_login_sent_lowercase(self):
        # Договорённость: портал шлёт email канонически в нижнем регистре —
        # регистр соответствия в 1С (PostgreSQL) регистрочувствителен.
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["Login"] == "u.mage@mage.ru"
            return httpx.Response(200, json={"Токен": "tok"})

        _install_raw(handler)
        await client._request_token(client._get_client(), TOKEN_BASE, AUTH, "  U.Mage@MAGE.ru  ")

    async def test_token_missing_field_is_error(self):
        _install_raw(lambda request: httpx.Response(200, json={}))
        with pytest.raises(ErpApprovalsError):
            await client._request_token(client._get_client(), TOKEN_BASE, AUTH, "u@mage.ru")

    async def test_token_transport_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        _install_raw(handler)
        with pytest.raises(ErpTransportError):
            await client._request_token(client._get_client(), TOKEN_BASE, AUTH, "u@mage.ru")

    async def test_token_cache_roundtrip(self):
        redis = FakeRedis()
        await client._cache_token(redis, "u@mage.ru", "tok")
        assert await client._get_cached_token(redis, "u@mage.ru") == "tok"
        await client.invalidate_token(redis, "u@mage.ru")
        assert await client._get_cached_token(redis, "u@mage.ru") is None

    async def test_cache_none_redis_is_noop(self):
        assert await client._get_cached_token(None, "u") is None
        await client._cache_token(None, "u", "tok")  # не падает
        await client.invalidate_token(None, "u")


class TestDocuments:
    async def test_normalization_supplier_order(self):
        _install(lambda request: httpx.Response(200, json=[_doc_supplier()]))
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "U@MAGE.ru")
        assert len(docs) == 1
        doc = docs[0]
        assert doc.doc_type == "ЗаказПоставщику"
        assert doc.number == "УП-0001"
        assert doc.contractor == "ООО Поставщик"
        assert doc.amount == 1234.56  # «1 234,56» → float
        assert doc.currency == "EUR"
        assert doc.has_prices is True
        assert doc.requires_manager is False
        assert doc.products[0].price == 10.5
        assert doc.products[0].total == 1260
        assert doc.history[0].stage == "Начало"
        assert doc.managers[0].guid == "m-1"

    async def test_products_recipient_parsed(self):
        # v2.1.0.0: «Получатель» — подразделение-получатель строки; у
        # внутренних заказов это шапочное подразделение (одинаково во всех
        # строках). Приходит у обоих типов документов.
        _install(
            lambda request: httpx.Response(
                200,
                json=[
                    _doc_supplier(
                        Товары=[_doc_supplier()["Товары"][0] | {"Получатель": "База флота"}]
                    ),
                    _doc_internal(
                        Товары=[{"Номенклатура": "Смазка", "Получатель": "Отдел ИТ, Мурманск"}]
                    ),
                ],
            )
        )
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert docs[0].products[0].recipient == "База флота"
        assert docs[1].products[0].recipient == "Отдел ИТ, Мурманск"

    async def test_products_recipient_absent_is_empty(self):
        _install(lambda request: httpx.Response(200, json=[_doc_supplier()]))
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert doc.products[0].recipient == ""

    async def test_sed_link_parsed(self):
        # «СсылкаНаЗадачуСЭД»: заполненная гиперссылка отдаётся как есть;
        # пустая строка (нет задачи СЭД) и отсутствие поля (внутренние
        # заказы) — в None, чтобы UI скрыл строку.
        filled = _doc_supplier(
            guid="g-sed",
            СсылкаНаЗадачуСЭД="https://sed.mage.ru/client/#/card/abc/316463",
        )
        empty = _doc_supplier(guid="g-empty", СсылкаНаЗадачуСЭД="")
        blank = _doc_supplier(guid="g-blank", СсылкаНаЗадачуСЭД="   ")
        # _doc_supplier не кладёт поле вовсе — «g-blank»-подобный отсутствующий
        absent = _doc_supplier(guid="g-absent")
        assert "СсылкаНаЗадачуСЭД" not in absent
        _install(lambda request: httpx.Response(200, json=[filled, empty, blank, absent]))
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert docs[0].sed_url == "https://sed.mage.ru/client/#/card/abc/316463"
        assert docs[1].sed_url is None
        assert docs[2].sed_url is None
        assert docs[3].sed_url is None

    async def test_nbsp_amounts_are_parsed(self):
        # 1С шлёт суммы строкой с неразрывными пробелами в разрядах
        # («10\xa0108,7») — иначе float падал и сумма/цены «исчезали»
        # (прод-кейс 2026-09-05).
        _install(
            lambda request: httpx.Response(
                200,
                json=[
                    _doc_supplier(
                        СуммаДокумента="10\xa0108,7",
                        Товары=[
                            {
                                "Номенклатура": "Проживание",
                                "Количество": "1",
                                "Цена": "2\xa0846,01",
                                "СуммаСНДС": "2\xa0988,31",
                            },
                        ],
                    )
                ],
            )
        )
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert doc.amount == 10108.7
        assert doc.products[0].price == 2846.01
        assert doc.products[0].total == 2988.31

    async def test_history_trimmed_to_last_process_start(self):
        # Перезапуск согласования: всё до последнего «Процесс запущен» —
        # остатки остановленного прогона, согласующему не показываем.
        raw = [
            {
                "Период": "01.09",
                "Пользователь": "А",
                "Событие": "Процесс запущен",
                "Комментарий": "",
            },
            {
                "Период": "02.09",
                "Пользователь": "Б",
                "Событие": "Этап согласован",
                "Комментарий": "",
            },
            {
                "Период": "03.09",
                "Пользователь": "В",
                "Событие": "Процесс остановлен",
                "Комментарий": "",
            },
            {
                "Период": "04.09",
                "Пользователь": "Г",
                "Событие": "Процесс запущен",
                "Комментарий": "",
            },
            {
                "Период": "05.09",
                "Пользователь": "Д",
                "Событие": "Этап согласован",
                "Комментарий": "",
            },
        ]
        _install(lambda request: httpx.Response(200, json=[_doc_supplier(ИсторияСогласования=raw)]))
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert [h.event for h in doc.history] == ["Процесс запущен", "Этап согласован"]
        assert doc.history[0].user == "Г"

    async def test_history_without_start_marker_untouched(self):
        raw = [
            {
                "Период": "01.09",
                "Пользователь": "А",
                "Событие": "Этап согласован",
                "Комментарий": "",
            },
            {
                "Период": "02.09",
                "Пользователь": "Б",
                "Событие": "Этап согласован",
                "Комментарий": "",
            },
        ]
        _install(lambda request: httpx.Response(200, json=[_doc_supplier(ИсторияСогласования=raw)]))
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert len(doc.history) == 2

    async def test_history_stop_after_start_is_kept(self):
        # Останов без перезапуска: запуск и останов остаются видимыми.
        raw = [
            {
                "Период": "01.09",
                "Пользователь": "А",
                "Событие": "Процесс запущен",
                "Комментарий": "",
            },
            {
                "Период": "02.09",
                "Пользователь": "Б",
                "Событие": "Процесс остановлен",
                "Комментарий": "",
            },
        ]
        _install(lambda request: httpx.Response(200, json=[_doc_supplier(ИсторияСогласования=raw)]))
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert [h.event for h in doc.history] == ["Процесс запущен", "Процесс остановлен"]

    async def test_internal_order_hides_prices(self):
        _install(lambda request: httpx.Response(200, json=[_doc_internal()]))
        (doc,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert doc.has_prices is False
        assert doc.products[0].price is None  # нули 1С → None (скрытие цен)
        assert doc.products[0].total is None
        assert doc.contractor is None
        assert doc.activity_direction == "Бурение"

    async def test_requires_manager_new_field_wins(self):
        doc = _doc_internal()
        doc["ТребуетсяОтветственный"] = True
        _install(lambda request: httpx.Response(200, json=[doc]))
        (parsed,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert parsed.requires_manager is True

    async def test_requires_manager_new_field_false_beats_legacy(self):
        doc = _doc_internal()
        doc["ТребуетсяОтветственный"] = False
        doc["ИсторияСогласования"] = [
            {"ЭтапПроцесса": "Руководитель ЦЗ Заказа на внутреннее потребление"}
        ]
        _install(lambda request: httpx.Response(200, json=[doc]))
        (parsed,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert parsed.requires_manager is False

    async def test_requires_manager_legacy_stage_fallback(self):
        doc = _doc_internal()
        doc["ИсторияСогласования"] = [
            {"ЭтапПроцесса": "Руководитель ЦЗ Заказа на внутреннее потребление"}
        ]
        _install(lambda request: httpx.Response(200, json=[doc]))
        (parsed,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert parsed.requires_manager is True

    async def test_requires_manager_legacy_other_stage(self):
        doc = _doc_internal()
        doc["ИсторияСогласования"] = [{"ЭтапПроцесса": "Другой этап"}]
        _install(lambda request: httpx.Response(200, json=[doc]))
        (parsed,) = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert parsed.requires_manager is False

    async def test_legacy_error_set_body_raises_not_empty_list(self):
        # Было (легаси): 200 + {"Профиль не найден"} → пустой список «как в
        # старом PHP». С v2.1.0.0 это штатный ответ «токен невалиден» —
        # молчаливая пустая очередь маскировала бы проблему: теперь после
        # re-login и повтора поднимается честная ошибка.
        _install(lambda request: httpx.Response(200, text='{"Профиль не найден"}'))
        with pytest.raises(ErpApprovalsError):
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")

    async def test_http_500_raises_with_message(self):
        _install(lambda request: httpx.Response(500, json={"Message": "Сбой сервера 1С"}))
        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert exc_info.value.status_code == 500
        assert "Сбой сервера 1С" in str(exc_info.value)


class TestAttachments:
    def _entry(self, data: str | None = None) -> dict:
        raw = data if data is not None else base64.b64encode(b"PDFDATA").decode()
        return {"ДвоичныеДанные": f"#base64:{raw}\n", "ИмяФайла": "Счёт 1", "Расширение": "pdf"}

    async def test_meta_and_decode(self):
        entry = self._entry()
        _install(lambda request: httpx.Response(200, json=[entry]))
        entries = await client.get_attachments(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert client.attachment_name(entries[0]) == "Счёт 1.pdf"

        name, data = await client.get_attachment_file(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", 0)
        assert name == "Счёт 1.pdf"
        assert data == b"PDFDATA"

    async def test_name_without_extension(self):
        _install(
            lambda request: httpx.Response(
                200, json=[{"ДвоичныеДанные": "#base64:AAAA", "ИмяФайла": "file"}]
            )
        )
        name, data = await client.get_attachment_file(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", 0)
        assert name == "file"
        assert data == b"\x00\x00\x00"  # base64 «AAAA» = 3 нулевых байта

    async def test_index_out_of_range_404(self):
        _install(lambda request: httpx.Response(200, json=[]))
        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.get_attachment_file(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", 5)
        assert exc_info.value.status_code == 404

    async def test_broken_base64_is_error(self):
        _install(lambda request: httpx.Response(200, json=[{"ДвоичныеДанные": "#base64:!!!"}]))
        with pytest.raises(ErpApprovalsError):
            await client.get_attachment_file(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", 0)


class TestDecisions:
    async def test_approve_new_contract(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/GETAgreed")
            assert request.url.params["Document"] == "g-1"
            assert request.url.params["Employee"] == "m-1"
            assert request.url.params["Comment"] == "ок"
            return httpx.Response(200, json={"Result": "OK", "Message": "Согласовано"})

        _install(handler)
        message = await client.approve(
            BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", comment="ок", employee_guid="m-1"
        )
        assert message == "Согласовано"

    async def test_approve_legacy_plain_text(self):
        _install(lambda request: httpx.Response(200, text="Документ УП-1 - Согласован"))
        message = await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert "Согласован" in message

    async def test_reject_sends_comment(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/GETNotAgreed")
            assert request.url.params["Comment"] == "брак"
            return httpx.Response(200, json={"Result": "OK", "Message": "Отклонено"})

        _install(handler)
        message = await client.reject(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", comment="брак")
        assert message == "Отклонено"

    async def test_result_false_on_200_is_error(self):
        # Новый контракт мог бы прислать Result=false в 200 — трактуем как ошибку.
        _install(
            lambda request: httpx.Response(
                200, json={"Result": False, "Code": 403, "Message": "документ не в очереди"}
            )
        )
        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert exc_info.value.status_code == 403

    async def test_success_without_message_is_neutral_ok(self):
        _install(lambda request: httpx.Response(200, json={"Result": True}))
        message = await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert message == "OK"

    async def test_html_error_body_is_infra_error(self):
        # WAF-бан: HTML-страница 403 — НЕ «чужой документ», а инфраструктура
        # (чеклист 1С §1): транспортная ошибка, 502-семантика.
        _install(
            lambda request: httpx.Response(
                403,
                text="<html>You got banned permanently</html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        with pytest.raises(ErpTransportError):
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")

    async def test_result_error_raises_with_code(self):
        _install(
            lambda request: httpx.Response(
                200, json={"Result": "Error", "Code": 403, "Message": "не ваш документ"}
            )
        )
        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert exc_info.value.status_code == 403


class TestSeparateTokenUrl:
    async def test_token_and_documents_use_different_roots(self):
        """1С публикует GETTokenByLogin под …/hs/PortalAuth, документы — под
        …/hs/Auth (миграция 116): пути не должны перепутаться."""

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/GETTokenByLogin"):
                assert "/hs/PortalAuth/" in str(request.url)
                return httpx.Response(200, json={"Result": True, "Token": "tok"})
            assert "/hs/PortalAuth/" not in str(request.url)
            assert "/hs/Auth/" in str(request.url)
            return httpx.Response(200, json=[_doc_supplier()])

        _install_raw(handler)
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert len(docs) == 1


class TestTokenRetryOn401:
    async def test_silent_retoken_on_401(self):
        calls = {"docs": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/GETTokenByLogin"):
                return httpx.Response(200, json={"Токен": f"tok-{calls['docs']}"})
            calls["docs"] += 1
            if calls["docs"] == 1:
                return httpx.Response(401, json={"Message": "токен протух"})
            return httpx.Response(200, json=[_doc_supplier()])

        _install_raw(handler)
        redis = FakeRedis()
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru", redis)
        assert len(docs) == 1
        # После 401 в кэше — обновлённый токен (tok-0 испортился).
        assert await client._get_cached_token(redis, "u@mage.ru") == "tok-1"
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru", redis)
        assert len(docs) == 1
        # Всего запросов списка: 1 (401) + 1 (после re-token) + 1 (второй вызов).
        assert calls["docs"] == 3


class TestTokenInvalidBody:
    """v2.1.0.0: методы данных отвечают HTTP 200 всегда — протухший токен
    это текст в теле («{\\nПользователь по токену не найден\\n}»; в переписке
    1С фигурировало и «Профиль не найден»), а не 401. Клиент обязан: тихий
    re-login + один повтор, при повторном отказе — честная ошибка (НЕ пустой
    список и НЕ «успех» с текстом отказа в message)."""

    INVALID_BODY = "{\nПользователь по токену не найден\n}"

    @staticmethod
    def _invalid(text: str, status: int = 200) -> httpx.Response:
        return httpx.Response(
            status, text=text, headers={"content-type": "application/json; charset=UTF-8"}
        )

    def test_detection_variants(self):
        def resp(text: str, status: int = 200) -> httpx.Response:
            return self._invalid(text, status)

        assert client._body_says_token_invalid(resp(self.INVALID_BODY))
        assert client._body_says_token_invalid(resp('{"Профиль не найден"}'))
        assert client._body_says_token_invalid(resp("Профиль не найден"))
        # Нормальные тела данных — не ошибка токена
        assert not client._body_says_token_invalid(resp('[{"GUID": "…"}]'))
        assert not client._body_says_token_invalid(resp('{"Result": true, "Message": "ok"}'))
        assert not client._body_says_token_invalid(resp("Документ согласован"))
        # 401 обрабатывается честным кодом, детект тела не нужен
        assert not client._body_says_token_invalid(resp(self.INVALID_BODY, status=401))

    def _install_flaky(self, invalid_calls: int) -> dict:
        calls = {"docs": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/DocumentsForApproval"):
                calls["docs"] += 1
                if calls["docs"] <= invalid_calls:
                    return self._invalid(self.INVALID_BODY)
                return httpx.Response(200, json=[_doc_supplier()])
            return httpx.Response(200, json=[])

        _install(handler)
        return calls

    async def test_expired_token_relogin_and_retry(self):
        calls = self._install_flaky(invalid_calls=1)
        docs = await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert [d.number for d in docs] == ["УП-0001"]
        assert calls["docs"] == 2  # отказ по телу → re-token → повтор

    async def test_permanent_invalid_token_raises_not_empty_list(self):
        calls = self._install_flaky(invalid_calls=99)
        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert exc_info.value.status_code == 502
        assert "токен" in str(exc_info.value).lower() or "профиль" in str(exc_info.value).lower()
        assert calls["docs"] == 2  # один повтор, не бесконечный цикл

    async def test_approve_never_fake_success_on_invalid_token(self):
        # Согласование с протухшим токеном НЕ должно возвращать ok=True
        # с текстом отказа в message (v2.1.0.0 отвечает 200 и на отказ).
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/GETAgreed"):
                return self._invalid(self.INVALID_BODY)
            return httpx.Response(200, json=[])

        _install(handler)
        with pytest.raises(ErpApprovalsError):
            await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1", comment="ок")


class TestTimeouts:
    """Ревью 2026-09-05: явный ``timeout=None`` в httpx отключает ВСЕ четыре
    таймаута, перекрывая клиентские настройки, — зависшая 1С занимала
    соединения пула (max_connections=5) навсегда. Вызовы без специального
    таймаута обязаны наследовать настройки клиента. httpx кладёт итоговый
    таймаут в ``request.extensions['timeout']`` (словарь) — по нему и судим."""

    def _capture_client(self, seen: dict) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen.setdefault("timeouts", []).append(request.extensions.get("timeout"))
            if request.url.path.endswith("/GETTokenByLogin"):
                return httpx.Response(200, json={"Токен": "tok"})
            return httpx.Response(200, json=[_doc_supplier()])

        client._ERP_HTTP_CLIENT = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    async def test_documents_inherit_client_timeout(self):
        seen: dict = {}
        self._capture_client(seen)
        await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")
        assert seen["timeouts"][-1] == {
            "connect": 5.0,
            "read": 30.0,
            "write": 30.0,
            "pool": 30.0,
        }

    async def test_decision_inherits_client_timeout(self):
        # Регрессия: GETAgreed шёл с timeout=None (полностью без таймаутов).
        seen: dict = {}
        self._capture_client(seen)
        await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert seen["timeouts"][-1]["read"] == 30.0

    async def test_attachments_keep_extended_timeout(self):
        seen: dict = {}
        self._capture_client(seen)
        await client.get_attachments(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")
        assert seen["timeouts"][-1]["read"] == 120.0


class TestTransportErrorsWrapped:
    """Ревью 2026-09-05: сырой httpx-эксепшн из документных вызовов не ловится
    ``except ErpApprovalsError`` — партия роняла запрос в 500 (терялся
    частичный отчёт), одиночные эндпоинты отдавали 500 вместо 502. Обёртка
    в ErpTransportError — как в ``_request_token``."""

    async def test_connect_error_on_documents(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/GETTokenByLogin"):
                return httpx.Response(200, json={"Токен": "tok"})
            raise httpx.ConnectError("no route")

        _install_raw(handler)
        with pytest.raises(ErpTransportError):
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "u@mage.ru")

    async def test_read_timeout_on_decision(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/GETTokenByLogin"):
                return httpx.Response(200, json={"Токен": "tok"})
            raise httpx.ReadTimeout("slow ERP")

        _install_raw(handler)
        with pytest.raises(ErpTransportError):
            await client.approve(BASE, TOKEN_BASE, AUTH, "u@mage.ru", "g-1")


class TestPing:
    async def test_full_chain_token_issued(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/GETTokenByLogin")
            assert request.url.params["Login"] == "admin@mage.ru"
            return httpx.Response(200, json={"Result": True, "Token": "tok"})

        _install_raw(handler)
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "Admin@MAGE.ru")
        assert ok is True
        assert "токен" in message

    async def test_unmapped_login_is_ok_with_note(self):
        # Покрытие регистра неполное: 404 = креды/сервис ок, логин не сопоставлен.
        _install_raw(
            lambda request: httpx.Response(
                404, json={"Result": False, "Code": 404, "Message": "Логин не сопоставлен"}
            )
        )
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is True
        assert "не сопоставлен" in message

    async def test_bad_credentials_401(self):
        _install_raw(
            lambda request: httpx.Response(
                401, json={"Result": False, "Code": 401, "Message": "auth"}
            )
        )
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "401" in message

    async def test_json_error_without_content_type_is_contract(self):
        # 1С отдаёт JSON-ошибки БЕЗ Content-Type (живой тест-кейс):
        # 404 «логин не сопоставлен» должен распознаваться как контракт,
        # а не как WAF-инфраструктура.
        body = '{"Result": false, "Code": 404, "Message": "Логин портала не сопоставлен"}'.encode()
        _install_raw(lambda request: httpx.Response(404, content=body))
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is True
        assert "не сопоставлен" in message

        with pytest.raises(ErpApprovalsError) as exc_info:
            await client.get_documents(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert exc_info.value.status_code == 404

    async def test_html_ban_page_is_infra_fail(self):
        _install_raw(
            lambda request: httpx.Response(
                403, text="<html>banned</html>", headers={"content-type": "text/html"}
            )
        )
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "WAF" in message

    async def test_unreachable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        _install_raw(handler)
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "недоступна" in message

    async def test_200_html_without_token_is_not_success(self):
        # Ревью 2026-09-05: любой 200 считался успехом до проверки тела —
        # HTML-страница чужого сервера под неверным адресом давала зелёный ping.
        _install_raw(
            lambda request: httpx.Response(
                200, text="<html>welcome</html>", headers={"content-type": "text/html"}
            )
        )
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "без токена" in message

    async def test_200_json_without_token_is_not_success(self):
        _install_raw(lambda request: httpx.Response(200, json={"hello": "world"}))
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "без токена" in message

    async def test_404_html_body_is_not_success(self):
        # 404 = «логин не сопоставлен» только для честных ответов 1С;
        # HTML чужого сервера успехом не считается.
        _install_raw(
            lambda request: httpx.Response(
                404, text="<html>Not Found</html>", headers={"content-type": "text/html"}
            )
        )
        ok, message, _ = await client.ping(BASE, TOKEN_BASE, AUTH, "admin@mage.ru")
        assert ok is False
        assert "HTML" in message
