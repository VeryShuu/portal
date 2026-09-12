"""Unit tests for ``_require_metrics_token`` (app/middleware/metrics.py).

The dependency protects ``/metrics`` behind a shared secret stored in
``system.json::metrics_token``. Covers:

- No token configured → open access (closed-perimeter assumption)
- Token via ``Authorization: Bearer`` (canonical Prometheus transport)
- Token via ``X-Metrics-Token`` (legacy/custom header, ad-hoc curl)
- Case-insensitive ``Bearer`` scheme prefix
- Wrong/missing token → 403
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.middleware.metrics import _require_metrics_token

_TOKEN = "s3cret-metrics-token"


def _settings(with_token: bool):
    """Fake SystemSettings object exposing ``metrics_token``."""
    obj = type("S", (), {})()
    obj.metrics_token = _TOKEN if with_token else ""
    return obj


class TestRequireMetricsToken:
    async def test_no_token_configured_allows_open_access(self):
        # No metrics_token set → /metrics is open regardless of headers.
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=False),
        ):
            await _require_metrics_token(x_metrics_token="", authorization="")

    async def test_no_token_configured_allows_even_with_random_headers(self):
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=False),
        ):
            await _require_metrics_token(x_metrics_token="garbage", authorization="Bearer nope")

    async def test_authorization_bearer_accepted(self):
        # Canonical Prometheus transport: Authorization: Bearer <token>.
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            await _require_metrics_token(x_metrics_token="", authorization=f"Bearer {_TOKEN}")

    async def test_authorization_bearer_case_insensitive_scheme(self):
        # Some clients send "bearer" lowercase — scheme must be case-insensitive.
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            await _require_metrics_token(x_metrics_token="", authorization=f"bearer {_TOKEN}")

    async def test_x_metrics_token_header_accepted(self):
        # Legacy/custom header still works (ad-hoc curl, scripts).
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            await _require_metrics_token(x_metrics_token=_TOKEN, authorization="")

    async def test_bearer_preferred_when_both_headers_present(self):
        # If both headers present, Bearer wins (canonical). X-Metrics-Token
        # being wrong here must NOT cause a failure since Bearer is valid.
        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            await _require_metrics_token(
                x_metrics_token="wrong",
                authorization=f"Bearer {_TOKEN}",
            )

    async def test_missing_token_when_configured_returns_403(self):

        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                await _require_metrics_token(x_metrics_token="", authorization="")
            assert exc.value.status_code == 403

    async def test_wrong_bearer_token_returns_403(self):

        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                await _require_metrics_token(x_metrics_token="", authorization="Bearer wrong-token")
            assert exc.value.status_code == 403

    async def test_wrong_x_metrics_token_returns_403(self):

        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                await _require_metrics_token(x_metrics_token="wrong-token", authorization="")
            assert exc.value.status_code == 403

    async def test_authorization_without_bearer_prefix_ignored(self):
        # "Basic <token>" or bare token must not be accepted as Bearer.

        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                await _require_metrics_token(x_metrics_token="", authorization=f"Basic {_TOKEN}")
            assert exc.value.status_code == 403

    async def test_constant_time_compare_no_short_circuit(self):
        # Sanity: compare_digest used, not ==. Wrong token of same length
        # still 403 (no info leak via timing).

        with patch(
            "app.core.system_config.load_system_settings",
            return_value=_settings(with_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                await _require_metrics_token(
                    x_metrics_token="S3cret-metrics-tokex",  # 1 char diff, same len
                    authorization="",
                )
            assert exc.value.status_code == 403
