"""Unit-тесты для app/core/sentry.py::scrub_sensitive.

Покрытие:
- удаление чувствительных заголовков (Authorization, Cookie, X-CSRF-Token,
  case-insensitive)
- маскирование чувствительных полей body (password, client_secret и т.п.) для
  dict и Mapping
- маскирование чувствительных QS-параметров в query_string и url
- ранний возврат event'а без request или с request не-dict
- сохранение всех остальных полей нетронутыми
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.sentry import scrub_sensitive


def _event(request: Any) -> dict[str, Any]:
    return {"request": request, "level": "error"}


class TestScrubHeaders:
    def test_removes_authorization_cookie_csrf(self):
        event = _event(
            {
                "headers": {
                    "Authorization": "Bearer secret",
                    "Cookie": "session=abc",
                    "X-CSRF-Token": "csrf",
                    "User-Agent": "pytest",
                }
            }
        )
        result = scrub_sensitive(event, {})
        assert result is not None
        headers = result["request"]["headers"]
        assert "Authorization" not in headers
        assert "Cookie" not in headers
        assert "X-CSRF-Token" not in headers
        assert headers["User-Agent"] == "pytest"

    def test_header_match_is_case_insensitive(self):
        event = _event({"headers": {"authorization": "Bearer x", "COOKIE": "v"}})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["request"]["headers"] == {}

    def test_non_string_header_keys_are_kept(self):
        event = _event({"headers": {1: "numeric", "X-Trace": "abc"}})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["request"]["headers"] == {1: "numeric", "X-Trace": "abc"}

    def test_no_headers_key(self):
        event = _event({"url": "https://x.test/api"})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert "headers" not in result["request"]


class TestScrubBody:
    def test_dict_body_sensitive_fields_masked(self):
        event = _event({"data": {"password": "secret", "client_secret": "x", "email": "u@x"}})
        result = scrub_sensitive(event, {})
        assert result is not None
        data = result["request"]["data"]
        assert data["password"] == "***"
        assert data["client_secret"] == "***"
        assert data["email"] == "u@x"

    def test_all_sensitive_fields(self):
        event = _event(
            {
                "data": {
                    "password": "1",
                    "client_secret": "2",
                    "app_password": "3",
                    "smtp_password": "4",
                    "kept": "5",
                }
            }
        )
        result = scrub_sensitive(event, {})
        assert result is not None
        data = result["request"]["data"]
        assert data["password"] == "***"
        assert data["client_secret"] == "***"
        assert data["app_password"] == "***"
        assert data["smtp_password"] == "***"
        assert data["kept"] == "5"

    def test_dict_body_case_insensitive_keys(self):
        event = _event({"data": {"PASSWORD": "secret", "Client_Secret": "x"}})
        result = scrub_sensitive(event, {})
        assert result is not None
        data = result["request"]["data"]
        assert data["PASSWORD"] == "***"
        assert data["Client_Secret"] == "***"

    def test_mapping_body_non_dict_is_replaced_with_sanitized_dict(self):
        class FrozenMap(Mapping):
            def __init__(self, src: dict[str, Any]) -> None:
                self._src = src

            def __getitem__(self, key: str) -> Any:
                return self._src[key]

            def __iter__(self):
                return iter(self._src)

            def __len__(self) -> int:
                return len(self._src)

        event = _event({"data": FrozenMap({"password": "p", "name": "alice"})})
        result = scrub_sensitive(event, {})
        assert result is not None
        data = result["request"]["data"]
        assert isinstance(data, dict)
        assert data["password"] == "***"
        assert data["name"] == "alice"

    def test_non_mapping_body_left_untouched(self):
        event = _event({"data": "raw-string-body"})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["request"]["data"] == "raw-string-body"


class TestScrubQueryString:
    def test_query_string_masked(self):
        event = _event({"query_string": "token=abc&id_token=def&hint=u@x&keep=ok&api_key=k"})
        result = scrub_sensitive(event, {})
        assert result is not None
        qs = result["request"]["query_string"]
        assert "token=***" in qs
        assert "id_token=***" in qs
        assert "hint=***" in qs
        assert "api_key=***" in qs
        assert "keep=ok" in qs
        assert "abc" not in qs
        assert "def" not in qs

    def test_query_string_case_insensitive(self):
        event = _event({"query_string": "Token=abc&SECRET=x"})
        result = scrub_sensitive(event, {})
        assert result is not None
        qs = result["request"]["query_string"]
        assert "abc" not in qs
        assert "x" not in qs.split("=")[-1] or "***" in qs

    def test_empty_query_string_not_modified(self):
        event = _event({"query_string": ""})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["request"]["query_string"] == ""

    def test_url_with_query_masked(self):
        event = _event({"url": "https://portal.test/api/login?password=p&access_token=t&ok=1"})
        result = scrub_sensitive(event, {})
        assert result is not None
        url = result["request"]["url"]
        assert url.startswith("https://portal.test/api/login?")
        assert "password=***" in url
        assert "access_token=***" in url
        assert "ok=1" in url

    def test_url_without_query_left_alone(self):
        event = _event({"url": "https://portal.test/api/login"})
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["request"]["url"] == "https://portal.test/api/login"


class TestEarlyReturn:
    def test_event_without_request_returned_as_is(self):
        event = {"level": "warning", "message": "ok"}
        result = scrub_sensitive(event, {})
        assert result is event

    def test_event_with_non_dict_request_returned_as_is(self):
        event = {"request": "not-a-dict"}
        result = scrub_sensitive(event, {})
        assert result is event

    def test_other_fields_preserved(self):
        event = {
            "request": {"headers": {"Authorization": "x"}, "url": "https://x.test"},
            "user": {"id": 1},
            "tags": {"env": "test"},
        }
        result = scrub_sensitive(event, {})
        assert result is not None
        assert result["user"] == {"id": 1}
        assert result["tags"] == {"env": "test"}
