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

(
    while true; do
        sleep 5
        if [ -f "$NGINX_RELOAD_TRIGGER" ]; then
            rm -f "$NGINX_RELOAD_TRIGGER"
            nginx -s reload 2>/dev/null && echo "[portal-nginx] config reloaded" || echo "[portal-nginx] reload failed (nginx may not be ready yet)"
        fi
    done
) &

exec nginx -g "daemon off;"
