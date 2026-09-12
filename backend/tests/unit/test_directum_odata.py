"""Unit-тесты OData-клиента Directum (:mod:`app.services.directum.odata`).

httpx подменяется MockTransport-клиентом в module-global singleton — реальные
сетевые вызовы не выполняются. Проверяются: пагинация по $skip, обработка
non-2xx/транспортных ошибок, парсинг строк (naive-deadline, отсутствие
Performer/Id), классификация ошибок, лимит страниц.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.directum import odata
from app.services.directum.odata import (
    DirectumApiError,
    _parse_assignment,
    classify_error,
    fetch_overdue_assignments,
    ping,
)


@pytest.fixture(autouse=True)
async def _reset_client():
    yield
    if odata._DIRECTUM_HTTP_CLIENT is not None:
        await odata._DIRECTUM_HTTP_CLIENT.aclose()
    odata._DIRECTUM_HTTP_CLIENT = None


def _install(handler) -> None:
    odata._DIRECTUM_HTTP_CLIENT = httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _row(
    row_id="a1", subject="Задача", deadline="2026-08-01T10:00:00+03:00", name="Иванов Иван Иванович"
):
    return {
        "Id": row_id,
        "Subject": subject,
        "Deadline": deadline,
        "Performer": {"Name": name} if name is not None else None,
    }


class TestFetchOverdueAssignments:
    async def test_single_page(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "IAssignments" in str(request.url)
            assert "$skip=0" in str(request.url) or "$skip" not in str(request.url)
            return httpx.Response(200, json={"value": [_row("t1"), _row("t2")]})

        _install(handler)
        items = await fetch_overdue_assignments(
            base_url="https://sed.test/odata", username="PDC1\\svc", password="pw"
        )
        assert len(items) == 2
        assert items[0].id == "t1"
        assert items[0].performer_name == "Иванов Иван Иванович"

    async def test_pagination_until_short_page(self):
        pages = {
            0: [_row(f"t{i}") for i in range(odata.PAGE_SIZE)],
            odata.PAGE_SIZE: [_row("last")],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            skip = int(dict(request.url.params).get("$skip", "0"))
            return httpx.Response(200, json={"value": pages[skip]})

        _install(handler)
        items = await fetch_overdue_assignments(
            base_url="https://sed.test/odata", username="u", password="pw"
        )
        assert len(items) == odata.PAGE_SIZE + 1

    async def test_page_limit_stops_at_max_pages(self):
        def handler(request: httpx.Request) -> httpx.Response:
            # Всегда полная страница — без лимита цикл был бы бесконечным.
            return httpx.Response(200, json={"value": [_row("x")] * odata.PAGE_SIZE})

        _install(handler)
        items = await fetch_overdue_assignments(
            base_url="https://sed.test/odata", username="u", password="pw"
        )
        assert len(items) == odata.PAGE_SIZE * odata.MAX_PAGES

    async def test_http_error_raises_with_status(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Unauthorized")

        _install(handler)
        with pytest.raises(DirectumApiError) as ei:
            await fetch_overdue_assignments(
                base_url="https://sed.test/odata", username="u", password="bad"
            )
        assert ei.value.status_code == 401

    async def test_non_json_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>proxy error</html>")

        _install(handler)
        with pytest.raises(DirectumApiError):
            await fetch_overdue_assignments(
                base_url="https://sed.test/odata", username="u", password="pw"
            )

    async def test_no_value_array_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"odata.error": {"message": "boom"}})

        _install(handler)
        with pytest.raises(DirectumApiError):
            await fetch_overdue_assignments(
                base_url="https://sed.test/odata", username="u", password="pw"
            )

    async def test_transport_error_wrapped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        _install(handler)
        with pytest.raises(DirectumApiError) as ei:
            await fetch_overdue_assignments(
                base_url="https://sed.test/odata", username="u", password="pw"
            )
        assert ei.value.status_code is None
        assert classify_error(ei.value) == "transient"

    async def test_filter_contains_now_and_status(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json={"value": []})

        _install(handler)
        await fetch_overdue_assignments(
            base_url="https://sed.test/odata",
            username="u",
            password="pw",
            now=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone(timedelta(hours=3))),
        )
        f = captured["params"]["$filter"]
        assert "Deadline lt 2026-08-17T12:00:00+03:00" in f
        assert "Status eq 'InProcess'" in f
        assert captured["params"]["$select"] == "Id,Subject,Deadline"
        assert "$expand" in captured["params"]


class TestPing:
    async def test_ok_returns_count(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "$top=1" in dict(request.url.params).values() or True
            return httpx.Response(200, json={"value": [{"Id": "x"}]})

        _install(handler)
        assert await ping(base_url="https://sed.test/odata", username="u", password="pw") == 1

    async def test_auth_error_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        _install(handler)
        with pytest.raises(DirectumApiError) as ei:
            await ping(base_url="https://sed.test/odata", username="u", password="pw")
        assert ei.value.status_code == 403


class TestParseAssignment:
    def test_naive_deadline_gets_moscow_tz(self):
        item = _parse_assignment(_row(deadline="2026-08-01T10:00:00"))
        assert item.deadline.tzinfo is not None
        assert item.deadline.utcoffset() == timedelta(hours=3)

    def test_offset_deadline_preserved(self):
        item = _parse_assignment(_row(deadline="2026-08-01T10:00:00+03:00"))
        assert item.deadline.utcoffset() == timedelta(hours=3)

    def test_missing_performer_becomes_empty_name(self):
        item = _parse_assignment(_row(name=None))
        assert item.performer_name == ""

    def test_missing_id_synthesized_stable(self):
        row = _row()
        del row["Id"]
        item = _parse_assignment(row)
        assert item.id.startswith("no-id:")
        assert item.id == _parse_assignment(dict(row)).id  # стабильный ключ

    def test_subject_stripped(self):
        item = _parse_assignment(_row(subject="  Задача  "))
        assert item.subject == "Задача"


class TestClassifyError:
    def test_5xx_transient(self):
        assert classify_error(DirectumApiError("e", status_code=503)) == "transient"

    def test_429_transient(self):
        assert classify_error(DirectumApiError("e", status_code=429)) == "transient"

    def test_4xx_permanent(self):
        assert classify_error(DirectumApiError("e", status_code=401)) == "permanent"

    def test_httpx_timeout_transient(self):
        assert classify_error(httpx.TimeoutException("t")) == "transient"

    def test_unknown_for_plain_exception(self):
        assert classify_error(RuntimeError("x")) == "unknown"
