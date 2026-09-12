#!/bin/sh
# nginx container entrypoint.
#
# Config files in /data/nginx-conf are produced by the `nginx-config`
# sidecar (see ./nginx/Dockerfile.config + render-config.sh). This
# container only runs nginx and reloads it whenever the sidecar (or the
# backend's manual /admin/system/nginx/reload endpoint) touches
# /data/nginx/reload-trigger.
set -e

NGINX_RELOAD_TRIGGER="/data/nginx/reload-trigger"
NGINX_CONF_DIR="/data/nginx-conf"

# Wait for the sidecar to render configs (compose health-gate already
# enforces this, but be defensive in case of misconfiguration).
WAIT_LIMIT=30
while [ ! -s "$NGINX_CONF_DIR/ssl_server.conf" ] && [ "$WAIT_LIMIT" -gt 0 ]; do
    echo "[portal-nginx] waiting for nginx-config sidecar to render configs..." >&2
    sleep 1
    WAIT_LIMIT=$((WAIT_LIMIT - 1))
done
if [ ! -s "$NGINX_CONF_DIR/ssl_server.conf" ]; then
    echo "[portal-nginx] FATAL: nginx-config sidecar produced no ssl_server.conf" >&2
    exit 1
fi

RELOAD_DIR="$(dirname "$NGINX_RELOAD_TRIGGER")"
TRIGGER_NAME="$(basename "$NGINX_RELOAD_TRIGGER")"

if command -v inotifywait >/dev/null 2>&1; then
    (
        trap 'exit 0' TERM INT
        # A trigger is written by backend/nginx-config. This mount is read-only
        # here, so nginx observes it but never deletes shared state.
        if [ -f "$NGINX_RELOAD_TRIGGER" ]; then
            nginx -s reload 2>/dev/null && echo "[portal-nginx] config reloaded (startup)" || echo "[portal-nginx] reload skipped (nginx not ready)"
        fi
        # ``touch`` updates an existing trigger, so watch close_write too.
        inotifywait -m -q -e close_write -e create -e moved_to --format '%f' "$RELOAD_DIR" | while read -r changed; do
            if [ "$changed" = "$TRIGGER_NAME" ]; then
                nginx -s reload 2>/dev/null && echo "[portal-nginx] config reloaded" || echo "[portal-nginx] reload failed (nginx may not be ready yet)"
            fi
        done
    ) &
else
    echo "[portal-nginx] WARNING: inotify-tools not installed, falling back to polling"
    (
        trap 'exit 0' TERM INT
        last_mtime=""
        while true; do
            sleep 1
            if [ -f "$NGINX_RELOAD_TRIGGER" ]; then
                current_mtime=$(stat -c %Y "$NGINX_RELOAD_TRIGGER" 2>/dev/null || true)
                if [ -n "$current_mtime" ] && [ "$current_mtime" != "$last_mtime" ]; then
                    last_mtime="$current_mtime"
                    nginx -s reload 2>/dev/null && echo "[portal-nginx] config reloaded" || echo "[portal-nginx] reload failed (nginx may not be ready yet)"
                fi
            fi
        done
    ) &
fi
WATCHER_PID=$!

cleanup() {
    kill "$WATCHER_PID" 2>/dev/null
    wait "$WATCHER_PID" 2>/dev/null
}
trap cleanup EXIT TERM INT

exec nginx -g "daemon off;"
