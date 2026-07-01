#!/bin/sh
# Init/sidecar entrypoint for the nginx-config service.
#
# 1. Renders nginx include configs once on startup (synchronously).
# 2. Watches /data/settings (system.json) and /data/certs (portal.crt/key)
#    for changes via inotify; on any relevant event re-renders the configs
#    and touches the reload trigger consumed by the nginx container.

set -eu

SETTINGS_DIR="${SETTINGS_DIR:-/data/settings}"
CERTS_DIR="${CERTS_DIR:-/data/certs}"

mkdir -p "$SETTINGS_DIR" "$CERTS_DIR"

render() {
    if ! /usr/local/bin/render-config.sh; then
        echo "[nginx-config] render failed (will retry on next event)" >&2
    fi
}

# Initial render — must succeed before nginx considers this service healthy.
# Retry up to 3 times with a short delay to handle the bind-mount race where
# the volume file may not yet be executable the instant the container starts.
_rendered=0
for _try in 1 2 3; do
    if /usr/local/bin/render-config.sh; then
        _rendered=1
        break
    fi
    echo "[nginx-config] initial render failed (attempt $_try/3), retrying in 1s..." >&2
    sleep 1
done
[ "$_rendered" = "0" ] && echo "[nginx-config] initial render failed after 3 attempts" >&2

if ! command -v inotifywait >/dev/null 2>&1; then
    echo "[nginx-config] WARNING: inotify-tools missing, falling back to 60s polling" >&2
    while true; do
        sleep 60
        render
    done
fi

# Watch parent directories: backend writes via os.replace (MOVED_TO) and
# the TLS upload handler writes/unlinks portal.crt / portal.key directly.
exec inotifywait -m -q \
    -e close_write -e moved_to -e create -e delete -e move \
    --format '%w%f' \
    "$SETTINGS_DIR" "$CERTS_DIR" \
    | while read -r path; do
        case "$path" in
            "$SETTINGS_DIR"/system.json|"$SETTINGS_DIR"/system.json.tmp.*)
                render
                ;;
            "$CERTS_DIR"/portal.crt|"$CERTS_DIR"/portal.key)
                render
                ;;
        esac
    done
