from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_HEADERS = {"authorization", "cookie", "x-csrf-token"}
_SENSITIVE_FIELDS = {"password", "client_secret", "app_password", "smtp_password"}
_SENSITIVE_QS_PARAMS = re.compile(
    r"(?i)(token|access_token|id_token|hint|secret|password|key|api_key)=[^&]*",
    re.IGNORECASE,
)


def scrub_sensitive(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    headers = request.get("headers")
    if isinstance(headers, dict):
        normalized: dict[str, Any] = {}
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_HEADERS:
                continue
            normalized[key] = value
        request["headers"] = normalized

    data = request.get("data")
    if isinstance(data, dict):
        for key in list(data.keys()):
            if isinstance(key, str) and key.lower() in _SENSITIVE_FIELDS:
                data[key] = "***"
    elif isinstance(data, Mapping):
        sanitized = dict(data)
        for key in list(sanitized.keys()):
            if isinstance(key, str) and key.lower() in _SENSITIVE_FIELDS:
                sanitized[key] = "***"
        request["data"] = sanitized

    qs = request.get("query_string")
    if isinstance(qs, str) and qs:
        request["query_string"] = _SENSITIVE_QS_PARAMS.sub(r"\1=***", qs)

    url = request.get("url")
    if isinstance(url, str) and "?" in url:
        path, _, qpart = url.partition("?")
        request["url"] = path + "?" + _SENSITIVE_QS_PARAMS.sub(r"\1=***", qpart)

    return event
