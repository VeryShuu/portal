#!/bin/sh
set -e

NGINX_CONF_DIR="/data/nginx-conf"
NGINX_RELOAD_TRIGGER="/data/nginx/reload-trigger"

mkdir -p "$NGINX_CONF_DIR"
mkdir -p "/data/nginx"
mkdir -p "/data/certs"

if [ ! -f "$NGINX_CONF_DIR/limits.conf" ]; then
    echo "client_max_body_size 100m;" > "$NGINX_CONF_DIR/limits.conf"
fi

if [ ! -f "$NGINX_CONF_DIR/allowlist.conf" ]; then
    cat > "$NGINX_CONF_DIR/allowlist.conf" << 'CONFEOF'
geo $allowed_network {
    default 0;
    10.0.0.0/8 1;
    172.16.0.0/12 1;
    192.168.0.0/16 1;
    127.0.0.1 1;
}
CONFEOF
fi

if [ ! -f "$NGINX_CONF_DIR/ssl_server.conf" ]; then
    cat > "$NGINX_CONF_DIR/ssl_server.conf" << 'SRVEOF'
# Default HTTP-only mode — backend will regenerate on startup
server {
    listen 80;
    server_name _;

    location /.well-known/acme-challenge/ {
        root /var/www/acme;
    }

    if ($allowed_network = 0) {
        return 403;
    }

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "0" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'" always;

    set $backend_host  "backend:8000";
    set $frontend_host "frontend:80";

    location /api/ {
        proxy_pass         http://$backend_host;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    location ~ ^/(health|ready)$ {
        proxy_pass         http://$backend_host;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass         http://$frontend_host;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }
}
SRVEOF
fi

(
    trap 'exit 0' TERM INT
    while true; do
        sleep 1
        if [ -f "$NGINX_RELOAD_TRIGGER" ]; then
            rm -f "$NGINX_RELOAD_TRIGGER"
            nginx -s reload 2>/dev/null && echo "[portal-nginx] config reloaded" || echo "[portal-nginx] reload failed (nginx may not be ready yet)"
        fi
    done
) &
WATCHER_PID=$!

cleanup() {
    kill "$WATCHER_PID" 2>/dev/null
    wait "$WATCHER_PID" 2>/dev/null
}
trap cleanup EXIT TERM INT

exec nginx -g "daemon off;"
