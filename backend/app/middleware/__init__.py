"""Middleware registration for the portal FastAPI application.

FastAPI/Starlette applies middleware in REVERSE registration order:
the last call to add_middleware / app.middleware("http") becomes the outermost
wrapper and therefore executes FIRST on incoming requests.

Desired request-processing order (outermost → innermost):
  [metrics]  →  logging  →  session  →  security_headers  →  csrf
  →  CORS  →  idempotency  →  routes

Registration order in install_middleware must be the mirror of the above:
  idempotency  →  CORS  →  csrf  →  security_headers  →  session
  →  logging  →  [metrics]
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.csrf import csrf_protection
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.logging import request_logging
from app.middleware.security_headers import security_headers
from app.middleware.session import session_sliding_window


def install_middleware(app: FastAPI) -> None:
    """Register all middleware in the correct order.

    Call this once during application construction, before any routes are registered.
    """
    from app.core.config import get_settings
    from app.core.system_config import load_system_settings

    settings = get_settings()
    sys_settings = load_system_settings()

    app.add_middleware(IdempotencyMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[sys_settings.portal_base_url or settings.portal_base_url],
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    )

    app.middleware("http")(csrf_protection)
    app.middleware("http")(security_headers)
    app.middleware("http")(session_sliding_window)
    app.middleware("http")(request_logging)

    if sys_settings.prometheus_metrics_enabled:
        from app.middleware.metrics import setup_metrics

        setup_metrics(app)
