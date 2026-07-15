"""Unit-тесты извлечения диагностического контекста из ошибки Keycloak refresh.

Покрывает ``app.api.auth.me._extract_kc_error_context`` — функцию, которая
вытягивает статус-код и тело ответа Keycloak из исключения, чтобы залогировать
их в ``auth.refresh_failed``. Тело при 400 (``{"error":"invalid_grant",...}``)
позволяет отличить «refresh-токен протух» от «Keycloak лежит/5xx» — без него
Keycloak-инциденты недиагностируемы (как было 13–14 июля).

Изолированные тесты, без HTTP/app — HTTP-путь refresh-эндпоинта в unit-окружении
перекрыт FastAPILimiter-init ошибкой, поэтому логика вынесена в чистую функцию.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from app.api.auth.me import _extract_kc_error_context


def _http_status_error(status_code: int, text: str) -> httpx.HTTPStatusError:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = text
    return httpx.HTTPStatusError(
        f"{status_code} Error", request=MagicMock(), response=mock_response
    )


def test_extracts_400_body_with_invalid_grant() -> None:
    """400 + invalid_grant — типичный «протухший/отозванный refresh-токен»."""
    exc = _http_status_error(400, '{"error": "invalid_grant"}')
    ctx = _extract_kc_error_context(exc)
    assert ctx == {"kc_status_code": 400, "kc_response": '{"error": "invalid_grant"}'}


def test_extracts_503_body_for_transient_keycloak_outage() -> None:
    """5xx от Keycloak — транзиентный сбой; тело (часто HTML) логируем тоже."""
    exc = _http_status_error(503, "<html>Service Unavailable</html>")
    ctx = _extract_kc_error_context(exc)
    assert ctx == {"kc_status_code": 503, "kc_response": "<html>Service Unavailable</html>"}


def test_extracts_other_status_codes() -> None:
    exc = _http_status_error(401, '{"error": "invalid_token"}')
    ctx = _extract_kc_error_context(exc)
    assert ctx == {"kc_status_code": 401, "kc_response": '{"error": "invalid_token"}'}


def test_non_http_error_returns_none_context() -> None:
    """Сетевые/таймаут-ошибки (не HTTPStatusError) — тела ответа нет."""
    ctx = _extract_kc_error_context(httpx.ConnectTimeout("timed out"))
    assert ctx == {"kc_status_code": None, "kc_response": None}
    ctx = _extract_kc_error_context(RuntimeError("unexpected"))
    assert ctx == {"kc_status_code": None, "kc_response": None}


def test_response_text_access_failure_is_swallowed() -> None:
    """Если .text бросает (стрим уже закрыт и т.п.) — не роняем refresh-флоу.

    Контекст kc_status_code всё равно сохраняется (он доступен всегда),
    kc_response становится None.
    """
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    type(mock_response).text = property(lambda self: (_ for _ in ()).throw(RuntimeError("closed")))
    exc = httpx.HTTPStatusError("400", request=MagicMock(), response=mock_response)

    ctx = _extract_kc_error_context(exc)
    assert ctx["kc_status_code"] == 400
    assert ctx["kc_response"] is None
