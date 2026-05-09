"""Nginx integration helpers.

Historically this module wrote nginx include files directly from Python
(``generate_nginx_confs`` / ``generate_ssl_server_conf``). That was moved
to a dedicated ``nginx-config`` sidecar container which renders the
configs from templates in ``nginx/templates/`` (see
``nginx/render-config.sh``). The sidecar inotifies
``/data/settings/system.json`` and ``/data/certs/`` and re-renders on
any change, so the backend no longer touches nginx config files.

What remains here:

* :func:`_build_nginx_csp` — pure helper kept as the canonical Python
  reference for the Content-Security-Policy string. Nothing in the
  request path uses it (nginx is the single source for CSP); kept so
  security tests can verify the policy invariants and middleware
  reference it if needed.
* :func:`trigger_nginx_reload` — used by the manual
  ``POST /admin/system/nginx/reload`` endpoint to force an immediate
  reload without waiting for the inotify-driven sidecar cycle.
* ``_CERTS_DIR`` — path constant re-exported for the TLS upload handler.
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

_NGINX_RELOAD_DIR = Path("/data/nginx")
_NGINX_RELOAD_TRIGGER = _NGINX_RELOAD_DIR / "reload-trigger"
_CERTS_DIR = Path("/data/certs")


def _build_nginx_csp(nextcloud_url: str, video_gallery_url: str = "") -> str:
    """Build the Content-Security-Policy string with a dynamic frame-src.

    Mirrors the logic in ``nginx/render-config.sh`` so tests can assert
    invariants (no ``unsafe-eval``, no open ``https:`` wildcard in
    frame-src, NC origin appears verbatim, etc.). The actual policy
    served at runtime is produced by the sidecar from the same inputs.
    """
    from urllib.parse import urlparse as _urlparse

    frame_src_parts = ["'self'"]
    for url in (nextcloud_url, video_gallery_url):
        if url:
            _parsed = _urlparse(url)
            if _parsed.scheme and _parsed.netloc:
                origin = f"{_parsed.scheme}://{_parsed.netloc}"
                if origin not in frame_src_parts:
                    frame_src_parts.append(origin)
    frame_src = " ".join(frame_src_parts)
    return (
        f"default-src 'self'; "
        f"script-src 'self'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob: https:; "
        f"font-src 'self' data:; "
        f"connect-src 'self'; "
        f"frame-src {frame_src}; "
        f"media-src 'self' https:; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'"
    )


def trigger_nginx_reload() -> None:
    """Touch the reload trigger consumed by the nginx container.

    The sidecar already touches this file after every render; this
    helper exists for the explicit "reload now" admin button so admins
    don't have to wait for the next inotify cycle.
    """
    _NGINX_RELOAD_DIR.mkdir(parents=True, exist_ok=True)
    _NGINX_RELOAD_TRIGGER.touch()
    logger.info("system.nginx_reload_triggered")
