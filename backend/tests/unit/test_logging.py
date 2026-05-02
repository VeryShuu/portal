"""Unit-тесты системы структурированного логирования."""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest
import structlog

from app.core.logging import (
    MAX_VALUE_SIZE,
    REDACTED,
    _is_sensitive_key,
    _mask_email,
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    mask_pii_processor,
    redact_secrets_processor,
    truncate_large_values_processor,
)


# ---------------------------------------------------------------------------
# _is_sensitive_key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "PASSWORD",
        "user_password",
        "password_hash",
        "access_token",
        "refresh_token",
        "id_token",
        "session_id",
        "Authorization",
        "Cookie",
        "client_secret",
        "csrf_token",
        "api_key",
        "MY_PRIVATE_KEY",
    ],
)
def test_sensitive_keys_detected(key: str) -> None:
    assert _is_sensitive_key(key) is True


@pytest.mark.parametrize(
    "key",
    ["user_id", "email", "role", "request_id", "method", "status_code", "elapsed_ms"],
)
def test_non_sensitive_keys_pass(key: str) -> None:
    assert _is_sensitive_key(key) is False


# ---------------------------------------------------------------------------
# redact_secrets_processor
# ---------------------------------------------------------------------------


def test_redact_top_level() -> None:
    ev = redact_secrets_processor(None, "info", {"password": "p@ss", "user_id": "42"})
    assert ev["password"] == REDACTED
    assert ev["user_id"] == "42"


def test_redact_nested_dict() -> None:
    ev = redact_secrets_processor(
        None,
        "info",
        {"meta": {"refresh_token": "r", "ok": True}},
    )
    assert ev["meta"]["refresh_token"] == REDACTED
    assert ev["meta"]["ok"] is True


def test_redact_in_list_of_dicts() -> None:
    ev = redact_secrets_processor(
        None,
        "info",
        {"items": [{"access_token": "a"}, {"name": "n"}]},
    )
    assert ev["items"][0]["access_token"] == REDACTED
    assert ev["items"][1]["name"] == "n"


# ---------------------------------------------------------------------------
# mask_pii_processor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,masked",
    [
        ("a@b.com", "a***@b.com"),
        ("john.doe@company.local", "j***@company.local"),
        ("USER@DOMAIN.RU", "U***@DOMAIN.RU"),
    ],
)
def test_mask_email(raw: str, masked: str) -> None:
    assert _mask_email(raw) == masked


def test_mask_pii_processor_masks_email_in_event() -> None:
    ev = mask_pii_processor(None, "info", {"user_email": "john@company.local", "user_id": "uuid"})
    assert ev["user_email"] == "j***@company.local"
    assert ev["user_id"] == "uuid"


def test_mask_pii_does_not_touch_non_strings() -> None:
    ev = mask_pii_processor(None, "info", {"count": 42, "ok": True})
    assert ev == {"count": 42, "ok": True}


# ---------------------------------------------------------------------------
# truncate_large_values_processor
# ---------------------------------------------------------------------------


def test_truncate_large_string() -> None:
    big = "x" * (MAX_VALUE_SIZE + 100)
    ev = truncate_large_values_processor(None, "info", {"body": big})
    assert ev["body"].endswith("...[TRUNCATED]")
    assert len(ev["body"]) == MAX_VALUE_SIZE + len("...[TRUNCATED]")
    assert ev["_truncated_fields"] == ["body"]


def test_truncate_keeps_short_strings() -> None:
    ev = truncate_large_values_processor(None, "info", {"msg": "ok"})
    assert ev["msg"] == "ok"
    assert "_truncated_fields" not in ev


def test_truncate_handles_bytes() -> None:
    ev = truncate_large_values_processor(None, "info", {"blob": b"\x00\x01\x02"})
    assert ev["blob"].startswith("<bytes len=")


# ---------------------------------------------------------------------------
# end-to-end: configure_logging + JSON output
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_log() -> io.StringIO:
    """Перенастраивает root-logger на StringIO + JSON, отдаёт буфер."""
    buf = io.StringIO()
    configure_logging(environment="production", log_level="DEBUG", force_json=True)
    root = logging.getLogger()
    # подменяем handler на in-memory
    root.handlers = []
    handler = logging.StreamHandler(buf)
    formatter = root.handlers and root.handlers[0].formatter or None
    # переиспользуем конфигурацию: создадим formatter заново
    import structlog as _s

    handler.setFormatter(
        _s.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                _s.contextvars.merge_contextvars,
                _s.processors.TimeStamper(fmt="iso", utc=True),
                redact_secrets_processor,
                mask_pii_processor,
                truncate_large_values_processor,
            ],
            processors=[
                _s.stdlib.ProcessorFormatter.remove_processors_meta,
                _s.processors.JSONRenderer(),
            ],
        )
    )
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield buf
    clear_request_context()


def test_logger_emits_valid_json_with_redaction(captured_log: io.StringIO) -> None:
    logger = get_logger("test")
    logger.info("auth.login", user_id="42", password="topsecret", access_token="JWT")

    line = captured_log.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "auth.login"
    assert payload["user_id"] == "42"
    assert payload["password"] == REDACTED
    assert payload["access_token"] == REDACTED


def test_email_masked_in_output(captured_log: io.StringIO) -> None:
    logger = get_logger("test")
    logger.info("user.created", user_email="alice@company.local")

    payload = json.loads(captured_log.getvalue().strip().splitlines()[-1])
    assert payload["user_email"] == "a***@company.local"


def test_contextvars_propagate(captured_log: io.StringIO) -> None:
    logger = get_logger("test")
    bind_request_context(request_id="rid-123", user_id="u-7", role="admin")
    logger.info("test.event")

    payload = json.loads(captured_log.getvalue().strip().splitlines()[-1])
    assert payload["request_id"] == "rid-123"
    assert payload["user_id"] == "u-7"
    assert payload["role"] == "admin"


def test_clear_request_context_drops_bindings(captured_log: io.StringIO) -> None:
    logger = get_logger("test")
    bind_request_context(request_id="rid-X")
    clear_request_context()
    logger.info("after.clear")

    payload = json.loads(captured_log.getvalue().strip().splitlines()[-1])
    assert "request_id" not in payload


def test_bind_request_context_filters_none() -> None:
    """None-значения не должны попадать в contextvars (засоряют логи)."""
    clear_request_context()
    bind_request_context(user_id="u-1", role=None, ip=None)
    ctx = structlog.contextvars.get_contextvars()
    assert ctx.get("user_id") == "u-1"
    assert "role" not in ctx
    assert "ip" not in ctx
    clear_request_context()
