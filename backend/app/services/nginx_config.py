from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.system_config import SystemSettings

logger = get_logger(__name__)

_NGINX_CONF_DIR = Path("/data/nginx-conf")
_NGINX_RELOAD_DIR = Path("/data/nginx")
_NGINX_RELOAD_TRIGGER = _NGINX_RELOAD_DIR / "reload-trigger"
_CERTS_DIR = Path("/data/certs")

_HTTP_REDIRECT_SERVER_BLOCK = (
    "# Auto-generated — HTTP-to-HTTPS redirect\n"
    "server {\n"
    "    listen 80;\n"
    "    server_name _;\n"
    "\n"
    "    location /.well-known/acme-challenge/ {\n"
    "        root /var/www/acme;\n"
    "    }\n"
    "\n"
    "    location = /health {\n"
    "        access_log off;\n"
    "        return 200 '{\"status\":\"ok\"}';\n"
    "        add_header Content-Type application/json;\n"
    "    }\n"
    "\n"
    "    if ($allowed_network = 0) {\n"
    "        return 403;\n"
    "    }\n"
    "\n"
    "    return 301 https://$host$request_uri;\n"
    "}\n"
)

_PROXY_LOCATIONS_BLOCK = (
    "\n"
    '    set $backend_host  "backend:8000";\n'
    '    set $frontend_host "frontend:80";\n'
    "\n"
    "    # Prevent duplicate security headers: nginx is the single source of truth.\n"
    "    # The FastAPI security_headers middleware also sets these; hide its copies\n"
    "    # so that only the nginx-level headers (with dynamic frame-src) are sent.\n"
    "    proxy_hide_header Content-Security-Policy;\n"
    "    proxy_hide_header X-Frame-Options;\n"
    "    proxy_hide_header X-Content-Type-Options;\n"
    "    proxy_hide_header X-XSS-Protection;\n"
    "    proxy_hide_header Referrer-Policy;\n"
    "    proxy_hide_header Permissions-Policy;\n"
    "    proxy_hide_header Strict-Transport-Security;\n"
    "\n"
    "    # Static media served directly from disk (no FastAPI hop).\n"
    "    location /media/avatars/ {\n"
    "        alias /data/avatars/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800" always;\n'
    '        add_header X-Content-Type-Options "nosniff" always;\n'
    "        try_files $uri =404;\n"
    "    }\n"
    "\n"
    "    location /media/news/ {\n"
    "        alias /data/news_media/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800" always;\n'
    '        add_header X-Content-Type-Options "nosniff" always;\n'
    "        try_files $uri =404;\n"
    "    }\n"
    "\n"
    "    location /media/link_icons/ {\n"
    "        alias /data/link_icons/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800" always;\n'
    '        add_header X-Content-Type-Options "nosniff" always;\n'
    "        try_files $uri =404;\n"
    "    }\n"
    "\n"
    "    location /api/ {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Upgrade $http_upgrade;\n"
    '        proxy_set_header   Connection "";\n'
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    "        proxy_set_header   X-Forwarded-Proto $scheme;\n"
    "        proxy_read_timeout  300s;\n"
    "        proxy_send_timeout  300s;\n"
    "    }\n"
    "\n"
    "    location ~ ^/(health|ready)$ {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "    }\n"
    "\n"
    "    location /api/v1/notifications/stream {\n"
    "        proxy_pass             http://$backend_host;\n"
    "        proxy_http_version     1.1;\n"
    '        proxy_set_header       Connection "";\n'
    "        proxy_set_header       Host $host;\n"
    "        proxy_set_header       X-Real-IP $remote_addr;\n"
    "        proxy_read_timeout     3600s;\n"
    "        proxy_buffering        off;\n"
    "        proxy_cache            off;\n"
    "        chunked_transfer_encoding on;\n"
    "    }\n"
    "\n"
    "    location /metrics {\n"
    "        allow 10.0.0.0/8;\n"
    "        allow 172.16.0.0/12;\n"
    "        allow 192.168.0.0/16;\n"
    "        allow 127.0.0.1;\n"
    "        deny all;\n"
    "        proxy_pass http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header Host $host;\n"
    "    }\n"
    "\n"
    "    location /internal/kb-media/ {\n"
    "        internal;\n"
    "        alias /data/kb/media/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800, immutable";\n'
    "    }\n"
    "\n"
    "    location /internal/kb-files/ {\n"
    "        internal;\n"
    "        alias /data/kb/files/;\n"
    '        add_header Cache-Control "no-store";\n'
    "    }\n"
    "\n"
    "    location /internal/photos-thumbs/ {\n"
    "        internal;\n"
    "        alias /data/photos/thumbs/;\n"
    "        expires 7d;\n"
    '        add_header Cache-Control "public, max-age=604800, immutable";\n'
    "    }\n"
    "\n"
    "    location /internal/photos-originals/ {\n"
    "        internal;\n"
    "        alias /data/photos/originals/;\n"
    '        add_header Cache-Control "no-store";\n'
    '        add_header X-Content-Type-Options "nosniff";\n'
    "    }\n"
    "\n"
    "    location /internal/photos-zips/ {\n"
    "        internal;\n"
    "        alias /data/photos/zips/;\n"
    '        add_header Cache-Control "no-store";\n'
    '        add_header X-Content-Type-Options "nosniff";\n'
    "    }\n"
    "\n"
    "    # Server-to-server callback from Nextcloud richdocuments federation\n"
    "    location = /ocs/v2.php/apps/richdocuments/api/v1/federation {\n"
    "        proxy_pass         http://$backend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    "        proxy_set_header   X-Forwarded-Proto $scheme;\n"
    "    }\n"
    "\n"
    "    location / {\n"
    "        proxy_pass         http://$frontend_host;\n"
    "        proxy_http_version 1.1;\n"
    "        proxy_set_header   Host $host;\n"
    "        proxy_set_header   X-Real-IP $remote_addr;\n"
    "    }\n"
    "}\n"
)


def _build_nginx_csp(nextcloud_url: str, video_gallery_url: str = "") -> str:
    """Build CSP string for nginx config with dynamic frame-src.

    Single source of truth for CSP. The FastAPI security_headers middleware
    intentionally does NOT set Content-Security-Policy — nginx is the only
    layer that emits it (and uses ``proxy_hide_header`` to drop any upstream
    copy), so the policy stays consistent across proxied and direct
    responses.
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


def _build_ssl_server_block(nextcloud_url: str, video_gallery_url: str = "") -> str:
    """Return the HTTPS server block string with a dynamic CSP (frame-src includes NC origin)."""
    csp = _build_nginx_csp(nextcloud_url, video_gallery_url)
    return (
        "# Auto-generated by portal backend — do not edit manually\n"
        "# Regenerated when TLS certificates or system settings are updated via Admin UI\n"
        "server {\n"
        "    listen 443 ssl;\n"
        "    http2  on;\n"
        "    server_name _;\n"
        "\n"
        "    ssl_certificate     /data/certs/portal.crt;\n"
        "    ssl_certificate_key /data/certs/portal.key;\n"
        "\n"
        "    ssl_protocols       TLSv1.2 TLSv1.3;\n"
        "    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256;\n"  # noqa: E501
        "    ssl_prefer_server_ciphers off;\n"
        "    ssl_session_cache   shared:SSL:10m;\n"
        "    ssl_session_timeout 1d;\n"
        "    ssl_session_tickets off;\n"
        "\n"
        "    if ($allowed_network = 0) {\n"
        "        return 403;\n"
        "    }\n"
        "\n"
        '    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n'
        '    add_header X-Content-Type-Options    "nosniff" always;\n'
        '    add_header X-Frame-Options           "DENY" always;\n'
        '    add_header X-XSS-Protection          "0" always;\n'
        '    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;\n'
        '    add_header Permissions-Policy        "camera=(), microphone=(), geolocation=()" always;\n'  # noqa: E501
        f'    add_header Content-Security-Policy "{csp}" always;\n'
    ) + _PROXY_LOCATIONS_BLOCK


def _build_http_only_server_block(nextcloud_url: str, video_gallery_url: str = "") -> str:
    """Return the HTTP-only server block string with a dynamic CSP."""
    csp = _build_nginx_csp(nextcloud_url, video_gallery_url)
    return (
        "# Auto-generated — HTTP-only mode (no TLS configured)\n"
        "server {\n"
        "    listen 80;\n"
        "    server_name _;\n"
        "\n"
        "    location /.well-known/acme-challenge/ {\n"
        "        root /var/www/acme;\n"
        "    }\n"
        "\n"
        "    if ($allowed_network = 0) {\n"
        "        return 403;\n"
        "    }\n"
        "\n"
        '    add_header X-Content-Type-Options    "nosniff" always;\n'
        '    add_header X-Frame-Options           "DENY" always;\n'
        '    add_header X-XSS-Protection          "0" always;\n'
        '    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;\n'
        '    add_header Permissions-Policy        "camera=(), microphone=(), geolocation=()" always;\n'  # noqa: E501
        f'    add_header Content-Security-Policy "{csp}" always;\n'
    ) + _PROXY_LOCATIONS_BLOCK


def generate_ssl_server_conf(nextcloud_url: str = "", video_gallery_url: str = "") -> None:
    from app.core.system_config import atomic_write

    _NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)
    cert_path = _CERTS_DIR / "portal.crt"
    key_path = _CERTS_DIR / "portal.key"
    ssl_conf_path = _NGINX_CONF_DIR / "ssl_server.conf"

    if cert_path.exists() and key_path.exists():
        ssl_block = _build_ssl_server_block(nextcloud_url, video_gallery_url)
        atomic_write(ssl_conf_path, _HTTP_REDIRECT_SERVER_BLOCK + "\n" + ssl_block)
        logger.info("system.ssl_server_conf_generated")
    else:
        http_block = _build_http_only_server_block(nextcloud_url, video_gallery_url)
        atomic_write(ssl_conf_path, http_block)
        logger.info("system.ssl_server_conf_http_only")


def generate_nginx_confs(s: SystemSettings | None = None) -> None:
    from app.core.system_config import atomic_write, load_system_settings

    if s is None:
        s = load_system_settings()
    _NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)

    atomic_write(
        _NGINX_CONF_DIR / "limits.conf",
        f"client_max_body_size {s.max_upload_size_mb}m;\n",
    )

    cidr_list = [c.strip() for c in s.allowed_cidr.split(",") if c.strip()]
    lines = ["geo $allowed_network {", "    default 0;"]
    for cidr in cidr_list:
        lines.append(f"    {cidr} 1;")
    lines.append("    127.0.0.1 1;")
    lines.append("}")
    atomic_write(_NGINX_CONF_DIR / "allowlist.conf", "\n".join(lines) + "\n")

    generate_ssl_server_conf(nextcloud_url=s.nextcloud_url, video_gallery_url=s.video_gallery_url)

    logger.info(
        "system.nginx_confs_generated",
        max_mb=s.max_upload_size_mb,
        cidr_count=len(cidr_list),
    )


def trigger_nginx_reload() -> None:
    _NGINX_RELOAD_DIR.mkdir(parents=True, exist_ok=True)
    _NGINX_RELOAD_TRIGGER.touch()
    logger.info("system.nginx_reload_triggered")
