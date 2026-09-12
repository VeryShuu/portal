"""Exercise the actual application formatter, including foreign stdlib records."""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from collections.abc import Callable, Generator

import pytest
import structlog

from app.core.logging import (
    MANAGED_LOGGER_NAMES,
    NOISY_IN_PRODUCTION_LOGGERS,
    NOISY_LIBRARY_LOGGERS,
    bind_request_context,
    configure_logging,
    get_logger,
)


@pytest.fixture
def log_output(monkeypatch: pytest.MonkeyPatch) -> Generator[Callable[[bool], io.StringIO]]:
    for name in (*MANAGED_LOGGER_NAMES, *NOISY_LIBRARY_LOGGERS, *NOISY_IN_PRODUCTION_LOGGERS):
        logging.getLogger(name)
    config = structlog.get_config().copy()
    context = structlog.contextvars.get_contextvars().copy()
    loggers = [logging.getLogger()] + [
        item
        for item in logging.Logger.manager.loggerDict.values()
        if isinstance(item, logging.Logger)
    ]
    saved = [(lg, lg.handlers[:], lg.filters[:], lg.level, lg.propagate) for lg in loggers]

    def configure(force_json: bool) -> io.StringIO:
        output = io.StringIO()
        monkeypatch.setattr("sys.stdout", output)
        structlog.contextvars.clear_contextvars()
        configure_logging(force_json=force_json, service_name="portal-test")
        bind_request_context(request_id="mon-security-request", correlation_id="mon-security-job")
        return output

    yield configure
    structlog.configure(**config)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**context)
    for lg, handlers, filters, level, propagate in saved:
        lg.handlers = handlers
        lg.filters = filters
        lg.setLevel(level)
        lg.propagate = propagate


def _raise_with_locals() -> None:
    # Artificial markers, never copied from runtime configuration or logs.
    password = "local-" + "credential-canary"
    unrelated_name = {"nested": ["unlabelled-" + "local-canary"]}
    assert password and unrelated_name
    raise ValueError("safe diagnostic cause")


@pytest.mark.parametrize("force_json", [True, False], ids=["json", "text"])
@pytest.mark.parametrize("foreign", [False, True], ids=["structlog", "stdlib"])
def test_exception_chain_keeps_diagnostics_without_locals(
    log_output: Callable[[bool], io.StringIO], force_json: bool, foreign: bool
) -> None:
    output = log_output(force_json)
    logger = logging.getLogger("mon-security") if foreign else get_logger("mon-security")
    try:
        try:
            _raise_with_locals()
        except ValueError as exc:
            raise RuntimeError("safe outer failure") from exc
    except RuntimeError:
        logger.exception("monitoring.probe_failed")

    rendered = output.getvalue()
    assert "local-credential-canary" not in rendered
    assert "unlabelled-local-canary" not in rendered
    for expected in (
        "ValueError",
        "RuntimeError",
        "safe diagnostic cause",
        "safe outer failure",
        "_raise_with_locals",
        "monitoring.probe_failed",
        "mon-security-request",
        "mon-security-job",
    ):
        assert expected in rendered
    if force_json:
        payload = json.loads(rendered)
        assert payload["service"] == "portal-test"
        assert all(
            "locals" not in frame for stack in payload["exception"] for frame in stack["frames"]
        )


@pytest.mark.parametrize("force_json", [True, False], ids=["json", "text"])
@pytest.mark.parametrize("foreign", [False, True], ids=["structlog", "stdlib"])
def test_exception_group_notes_are_sanitized_after_rendering(
    log_output: Callable[[bool], io.StringIO], force_json: bool, foreign: bool
) -> None:
    output = log_output(force_json)
    logger = logging.getLogger("mon-security") if foreign else get_logger("mon-security")
    try:
        error = ValueError("request failed password=" + "exception-canary")
        error.add_note("access_token=" + "note-canary")
        raise ExceptionGroup("safe group", [error, RuntimeError("safe sibling")])
    except ExceptionGroup:
        logger.exception("monitoring.group_failed")
    rendered = output.getvalue()
    assert "exception-canary" not in rendered
    assert "note-canary" not in rendered
    assert "safe sibling" in rendered
    assert "ExceptionGroup" in rendered


@pytest.mark.parametrize("force_json", [True, False], ids=["json", "text"])
@pytest.mark.parametrize("foreign", [False, True], ids=["structlog", "stdlib"])
@pytest.mark.parametrize(
    ("message", "canary"),
    [
        ("failed https://svc:url-canary@service.invalid/path", "url-canary"),
        ("failed https://service.invalid/path?access_token=query-canary&limit=2", "query-canary"),
        ("Authorization: Bearer header-canary", "header-canary"),
        ("Cookie: portal_session=cookie-canary; other=also-private", "cookie-canary"),
        ("{'password': 'quoted canary with spaces'}", "quoted canary with spaces"),
    ],
    ids=["url-userinfo", "url-query", "authorization", "cookie", "quoted-value"],
)
def test_unstructured_messages_redact_recognizable_credentials(
    log_output: Callable[[bool], io.StringIO],
    force_json: bool,
    foreign: bool,
    message: str,
    canary: str,
) -> None:
    output = log_output(force_json)
    logger = logging.getLogger("mon-security") if foreign else get_logger("mon-security")
    logger.error(message)
    assert canary not in output.getvalue()
    assert "REDACTED" in output.getvalue()


@pytest.mark.parametrize("force_json", [True, False], ids=["json", "text"])
def test_nested_structured_values_and_safe_url_survive(
    log_output: Callable[[bool], io.StringIO], force_json: bool
) -> None:
    output = log_output(force_json)
    get_logger("mon-security").error(
        "monitoring.nested",
        metadata={"items": [{"password": "nested-canary", "status": "unavailable"}]},
        url="https://service.invalid/health?limit=2",
    )
    rendered = output.getvalue()
    assert "nested-canary" not in rendered
    assert "unavailable" in rendered
    assert "https://service.invalid/health?limit=2" in rendered


def test_repeated_sensitive_word_does_not_stall_log_processing() -> None:
    # Subprocess timeout bounds a regression without hanging the entire suite.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.logging import _redact_string; "
                "value = 'token' * 10000; "
                "assert _redact_string(value) == value"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
