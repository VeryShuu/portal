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
LEARN_URL=""
LOOPBACK_ALLOWED=0

if [ -f "$SETTINGS_JSON" ] && command -v jq >/dev/null 2>&1; then
    MAX_MB=$(jq -r '.max_upload_size_mb // empty' "$SETTINGS_JSON" 2>/dev/null || echo "")
    CIDR=$(jq -r '.allowed_cidr // empty'         "$SETTINGS_JSON" 2>/dev/null || echo "")
    NC_URL=$(jq -r '.nextcloud_url // empty'      "$SETTINGS_JSON" 2>/dev/null || echo "")
    VG_URL=$(jq -r '.video_gallery_url // empty'  "$SETTINGS_JSON" 2>/dev/null || echo "")
    LEARN_URL=$(jq -r '.learning_base_url // empty' "$SETTINGS_JSON" 2>/dev/null || echo "")
fi
LEARN_FRONTEND_HOST="${LEARN_FRONTEND_HOST:-frontend:81}"
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
        # 127.0.0.1/32 — это тот же лупбэк: без нормализации /32 генератор не
        # замечает уже прописанный в allowed_cidr лупбэк и дописывает второй →
        # nginx warning "duplicate network" при старте (косметика, но шумит).
        case "$c_trim" in
            127.0.0.1 | 127.0.0.1/32) LOOPBACK_ALLOWED=1 ;;
        esac
        [ -n "$c_trim" ] && printf '    %s 1;\n' "$c_trim"
    done
    [ "$LOOPBACK_ALLOWED" = "1" ] || printf '    127.0.0.1 1;\n'
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

# Trusted rich-content iframe origins — runtime-настройка system.json
# (Admin UI → System → video_iframe_origins; backend нормализует и валидирует).
# Разрешённые видеохостинги: rich-контент (новости/БЗ) и встроенные видео
# в материалах модуля обучения (портал + learn-контур).
# Fallback (поля нет в system.json / файл не читается) — дефолт из
# backend/app/core/constants.py::DEFAULT_VIDEO_IFRAME_ORIGINS: sidecar не может
# импортировать Python-константы, держите два дефолта равными (bats-тест).
# Пустой список в настройке = внешние iframe запрещены (frame-src 'self').
VIDEO_IFRAME_ORIGINS_DEFAULT="https://video.mage.ru https://www.youtube-nocookie.com https://rutube.ru https://vk.com https://vkvideo.ru https://player.vimeo.com"
VIDEO_IFRAME_ORIGINS="KEEP_DEFAULT"
if [ -f "$SETTINGS_JSON" ] && command -v jq >/dev/null 2>&1; then
    VIDEO_IFRAME_ORIGINS=$(jq -r 'if has("video_iframe_origins") then (.video_iframe_origins | join(" ")) else "KEEP_DEFAULT" end' "$SETTINGS_JSON" 2>/dev/null || echo "KEEP_DEFAULT")
fi
# Пустая строка от jq — осознанный пустой список (встраивание выключено):
# фолбэк только для маркера отсутствия поля.
[ "$VIDEO_IFRAME_ORIGINS" = "KEEP_DEFAULT" ] && VIDEO_IFRAME_ORIGINS="$VIDEO_IFRAME_ORIGINS_DEFAULT"
FRAME_SRC="'self'${VIDEO_IFRAME_ORIGINS:+ ${VIDEO_IFRAME_ORIGINS}}"
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

# ---------- learn_server.conf (публичный контур обучения, ADR-051) ----------
# Контур рендерится ТОЛЬКО при заданном learning_base_url И наличии
# TLS-сертификата (learn.crt/learn.key, иначе портал-пара — wildcard).
# Иначе файл — пустой комментарий: include в nginx.conf не ломается,
# публичный вход отсутствует (fail-closed).
LEARN_OUT="$OUT_DIR/learn_server.conf"
LEARN_HOST=""
LEARN_MODE="disabled"
if [ -n "$LEARN_URL" ]; then
    _origin=$(extract_origin "$LEARN_URL")
    # Fail-closed (PA-025): только https-origin. Явный http:// не рендерим —
    # публичный контур существует только как TLS (см. шаблон: HTTPS-блок +
    # redirect); HTTP-рендер дал бы ссылки восстановления (с токеном в query)
    # по незашифрованному каналу. Легаси http-значение => контур disabled,
    # оператор чинит настройку через Admin UI (API отвергает не-HTTPS).
    case "$_origin" in
        https://*) LEARN_HOST="${_origin#*://}" ;;
    esac
fi

# Выбор сертификата: отдельная learn-пара приоритетнее портал-пары.
if [ -f "$CERTS_DIR/learn.crt" ] && [ -f "$CERTS_DIR/learn.key" ]; then
    LEARN_CERT="$CERTS_DIR/learn.crt"
    LEARN_KEY="$CERTS_DIR/learn.key"
elif [ -f "$CERTS_DIR/portal.crt" ] && [ -f "$CERTS_DIR/portal.key" ]; then
    LEARN_CERT="$CERTS_DIR/portal.crt"
    LEARN_KEY="$CERTS_DIR/portal.key"
else
    LEARN_CERT=""
    LEARN_KEY=""
fi

if [ -n "$LEARN_HOST" ] && [ -n "$LEARN_CERT" ]; then
    # Внешний контент учебного контура — только доверенные видеохостинги
    # (встроенные видео в материалах курсов, VIDEO_IFRAME_ORIGINS выше):
    # media-src не открываем — плеер живёт внутри iframe хостинга.
    LEARN_CSP="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self' ${VIDEO_IFRAME_ORIGINS}; object-src 'none'; base-uri 'self'; form-action 'self'"
    TMP="$LEARN_OUT.tmp.$$"
    {
        LEARN_HOST="$LEARN_HOST" LEARN_CERT="$LEARN_CERT" LEARN_KEY="$LEARN_KEY" \
        LEARN_CSP="$LEARN_CSP" LEARN_FRONTEND_HOST="$LEARN_FRONTEND_HOST" \
        envsubst '${LEARN_HOST} ${LEARN_CERT} ${LEARN_KEY} ${LEARN_CSP} ${LEARN_FRONTEND_HOST}' \
        < "$TEMPLATES_DIR/learn_server.conf.tmpl"
    } > "$TMP"
    mv -f "$TMP" "$LEARN_OUT"
    LEARN_MODE="rendered (host=$LEARN_HOST)"
else
    TMP="$LEARN_OUT.tmp.$$"
    printf '# learn contour disabled: learning_base_url not set/not https, or TLS cert missing (ADR-051)\n' > "$TMP"
    mv -f "$TMP" "$LEARN_OUT"
fi

# ---------- trigger reload ----------
touch "$RELOAD_TRIGGER" 2>/dev/null || true

printf '[nginx-config] rendered (mode=%s, max_mb=%s, cidr=%s, learn=%s)\n' "$MODE" "$MAX_MB" "$CIDR" "$LEARN_MODE" >&2
