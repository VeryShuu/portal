#!/bin/sh
# Renders nginx include configs from /templates using values from
# /data/settings/system.json (mutable via Admin UI) and presence of TLS
# certificates in /data/certs.
#
# Output files (atomically replaced):
#   /data/nginx-conf/limits.conf      — client_max_body_size
#   /data/nginx-conf/allowlist.conf   — geo $allowed_network { ... }
#   /data/nginx-conf/ssl_server.conf  — server block(s): HTTP-only or HTTP+HTTPS
#
# After every successful render the reload trigger /data/nginx/reload-trigger
# is touched so the nginx container (which inotifies that path) reloads.

set -eu

TEMPLATES_DIR="${TEMPLATES_DIR:-/templates}"
SETTINGS_JSON="${SETTINGS_JSON:-/data/settings/system.json}"
CERTS_DIR="${CERTS_DIR:-/data/certs}"
OUT_DIR="${OUT_DIR:-/data/nginx-conf}"
RELOAD_TRIGGER="${RELOAD_TRIGGER:-/data/nginx/reload-trigger}"
FRONTEND_HOST="${FRONTEND_HOST:-frontend:80}"

# Defaults — must mirror app/core/system_config.py::_SystemSettingsBase.
DEFAULT_MAX_MB="${DEFAULT_MAX_UPLOAD_MB:-100}"
DEFAULT_CIDR="${DEFAULT_ALLOWED_CIDR:-10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"

mkdir -p "$OUT_DIR" "$(dirname "$RELOAD_TRIGGER")"

MAX_MB=""
CIDR=""
NC_URL=""
VG_URL=""

if [ -f "$SETTINGS_JSON" ] && command -v jq >/dev/null 2>&1; then
    MAX_MB=$(jq -r '.max_upload_size_mb // empty' "$SETTINGS_JSON" 2>/dev/null || echo "")
    CIDR=$(jq -r '.allowed_cidr // empty'         "$SETTINGS_JSON" 2>/dev/null || echo "")
    NC_URL=$(jq -r '.nextcloud_url // empty'      "$SETTINGS_JSON" 2>/dev/null || echo "")
    VG_URL=$(jq -r '.video_gallery_url // empty'  "$SETTINGS_JSON" 2>/dev/null || echo "")
fi
[ -z "$MAX_MB" ] && MAX_MB="$DEFAULT_MAX_MB"
[ -z "$CIDR" ]   && CIDR="$DEFAULT_CIDR"

# ---------- limits.conf ----------
TMP="$OUT_DIR/limits.conf.tmp.$$"
printf 'client_max_body_size %sm;\n' "$MAX_MB" > "$TMP"
mv -f "$TMP" "$OUT_DIR/limits.conf"

# ---------- allowlist.conf ----------
TMP="$OUT_DIR/allowlist.conf.tmp.$$"
{
    printf 'geo $allowed_network {\n'
    printf '    default 0;\n'
    OLD_IFS="$IFS"
    IFS=','
    # shellcheck disable=SC2086
    set -- $CIDR
    IFS="$OLD_IFS"
    for c in "$@"; do
        c_trim=$(printf '%s' "$c" | tr -d ' ')
        [ -n "$c_trim" ] && printf '    %s 1;\n' "$c_trim"
    done
    printf '    127.0.0.1 1;\n'
    printf '}\n'
} > "$TMP"
mv -f "$TMP" "$OUT_DIR/allowlist.conf"

# ---------- CSP (frame-src) ----------
extract_origin() {
    # Convert "https://host[:port]/path?..." → "https://host[:port]"
    # Empty input or input without "://" → empty output.
    # Pure POSIX sh — busybox awk's regex flavor is too limited.
    case "$1" in
        ""|*://*) ;;
        *) return ;;
    esac
    _scheme="${1%%://*}"
    case "$_scheme" in
        ""|*[!a-zA-Z0-9+.-]*) return ;;
    esac
    case "$_scheme" in
        [!a-zA-Z]*) return ;;
    esac
    _rest="${1#*://}"
    # Trim path, query, fragment.
    _host="${_rest%%/*}"
    _host="${_host%%\?*}"
    _host="${_host%%#*}"
    [ -z "$_host" ] && return
    printf '%s://%s' "$_scheme" "$_host"
}

FRAME_SRC="'self'"
for u in "$NC_URL" "$VG_URL"; do
    origin=$(extract_origin "$u")
    if [ -n "$origin" ]; then
        case " $FRAME_SRC " in
            *" $origin "*) ;;
            *) FRAME_SRC="$FRAME_SRC $origin" ;;
        esac
    fi
done

CSP="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://api.open-meteo.com https://geocoding-api.open-meteo.com; frame-src ${FRAME_SRC}; media-src 'self' https:; object-src 'none'; base-uri 'self'; form-action 'self'"

# ---------- ssl_server.conf ----------
TMP="$OUT_DIR/ssl_server.conf.tmp.$$"
if [ -f "$CERTS_DIR/portal.crt" ] && [ -f "$CERTS_DIR/portal.key" ]; then
    {
        cat "$TEMPLATES_DIR/http_redirect.conf.tmpl"
        printf '\n'
        CSP="$CSP" envsubst '${CSP}' < "$TEMPLATES_DIR/https_server.conf.tmpl"
        sed "s|frontend:80|$FRONTEND_HOST|g" "$TEMPLATES_DIR/proxy_locations.conf.tmpl"
    } > "$TMP"
    MODE="https"
else
    {
        CSP="$CSP" envsubst '${CSP}' < "$TEMPLATES_DIR/http_only_server.conf.tmpl"
        sed "s|frontend:80|$FRONTEND_HOST|g" "$TEMPLATES_DIR/proxy_locations.conf.tmpl"
    } > "$TMP"
    MODE="http-only"
fi
mv -f "$TMP" "$OUT_DIR/ssl_server.conf"

# ---------- trigger reload ----------
touch "$RELOAD_TRIGGER" 2>/dev/null || true

printf '[nginx-config] rendered (mode=%s, max_mb=%s, cidr=%s)\n' "$MODE" "$MAX_MB" "$CIDR" >&2
